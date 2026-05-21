"""Battle-state + attack helpers for the encounter-sim suite.

Mirrors the ``tests/harness/test_attack_auto_damage.py`` patterns —
``_mkc`` / ``_seed_battle`` / ``_set_auto_apply`` — but rewritten in
sync httpx for the Playwright sync test runtime. Centralising them
here so every encounter-sim test PUTs a known battle_state through
the same code path.
"""
from __future__ import annotations

import os

import httpx


BASE_URL = os.getenv("HARNESS_BASE_URL", "http://localhost:8013")
CAMPAIGN_ID = int(os.getenv("HARNESS_TEST_CAMPAIGN", "1"))


def _gm_client() -> httpx.Client:
    """Returns an ALREADY-OPEN logged-in client. Callers must call
    ``.close()`` (or use a try/finally) — do NOT wrap in ``with`` because
    the login call has already implicitly opened the client and httpx's
    context manager rejects a second open.
    """
    client = httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0)
    resp = client.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
    if resp.status_code not in (200, 303):
        client.close()
        raise AssertionError(f"GM login failed: {resp.status_code}")
    return client


def make_combatant(
    cid: str,
    *,
    char_id: int | None = None,
    name: str = "X",
    hp_cur: int = 30,
    hp_max: int = 30,
    initiative: int = 10,
    template_id: int | None = None,
) -> dict:
    """Build one combatant dict in the shape the realtime hub
    expects. Initiative defaults to 10; tests that care about turn
    order pass explicit values."""
    out: dict = {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": initiative,
        "hp_current": hp_cur,
        "hp_max": hp_max,
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
    }
    if template_id is not None:
        out["token_template_id"] = template_id
    return out


def _battle_state_dict(combatants: list[dict]) -> dict:
    return {
        "combatants": combatants,
        "turn_index": 0,
        "round": 1,
        "active": True,
    }


def seed_battle(combatants: list[dict]) -> None:
    """PUT a known battle state into the campaign's realtime hub.

    Server-side only — see ``seed_battle_into_page`` for the
    companion that primes the GM page's localStorage so the init
    tracker DOM actually renders the combatants. Tests typically
    want both: server side so /attack can find target IDs, page
    side so the DOM-layer assertions land.
    """
    client = _gm_client()
    try:
        resp = client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json=_battle_state_dict(combatants),
        )
        resp.raise_for_status()
    finally:
        client.close()


def seed_battle_into_page(context, combatants: list[dict]) -> None:
    """Pre-populate a Playwright browser context's ``localStorage``
    with the same battle state ``seed_battle`` PUTs to the server.

    Why this exists: the GM client treats localStorage as the source
    of truth for the init tracker and IGNORES ``battle_update`` WS
    broadcasts unless ``force_gm_sync`` is set (see
    tabletop.html:5543 — a v2.5.5-era guard against echo loops when
    the GM pushes their own edits). A test that PUTs state from a
    side client therefore never appears in the GM's view, even
    though the server stored it.

    Calling this BEFORE ``page.goto(...)`` (via
    ``context.add_init_script``) sets the localStorage entry so
    the page's init IIFE reads our seeded state on load. Pairs with
    ``seed_battle`` (server side) so /attack's target lookup and
    the GM's DOM both agree.
    """
    import json
    key = f"simplevtt_battle_{CAMPAIGN_ID}"
    state_json = json.dumps(_battle_state_dict(combatants))
    # ``add_init_script`` runs in EVERY new document context in this
    # browser context, before any page script runs. That's exactly
    # when the init IIFE reads localStorage.
    context.add_init_script(
        f"window.localStorage.setItem({json.dumps(key)}, {json.dumps(state_json)});"
    )


def set_auto_apply(on: bool) -> None:
    """Toggle the campaign's ``auto_apply_damage`` setting via the
    settings-form POST so attacks on hit produce a non-zero
    ``damage_applied`` and the bandit's HP actually drops in the
    init tracker.

    The settings endpoint expects the full form so a partial POST
    would null other fields; we send the demo defaults the harness
    already proved out in ``tests/harness/test_attack_auto_damage.py``.
    """
    form = {
        "name": "Demo Campaign",
        "description": "demo",
        "game_system": "dnd5e",
        "gm_tab_color": "",
        "font_override": "",
        "default_encounter_id": "",
        "hp_threshold_1": "",
        "hp_threshold_2": "",
        "hp_threshold_3": "",
        "hp_threshold_4": "",
        "auto_play_playlist_id": "",
        "auto_play_mode": "order",
        "auto_play_initial_volume": "0.7",
    }
    if on:
        form["auto_apply_damage"] = "on"
    client = _gm_client()
    try:
        resp = client.post(
            f"/campaign/{CAMPAIGN_ID}/settings",
            data=form,
            follow_redirects=False,
        )
        # 303 on success (form-POST redirect).
        if resp.status_code not in (200, 303):
            raise AssertionError(f"set_auto_apply failed: {resp.status_code} {resp.text}")
    finally:
        client.close()


def post_attack(
    character_id: int,
    attack_index: int,
    *,
    target_combatant_id: str | None = None,
    override: bool = True,
) -> httpx.Response:
    """POST ``/attack`` as the GM. Wraps the call so tests don't
    re-create a logged-in client each time. ``override=True`` bypasses
    the Phase 4 action-economy gate (per CLAUDE.md harness-test rules).
    """
    body: dict = {
        "character_id": character_id,
        "attack_index": attack_index,
        "override": override,
    }
    if target_combatant_id:
        body["target_combatant_id"] = target_combatant_id
    client = _gm_client()
    try:
        return client.post(f"/api/campaign/{CAMPAIGN_ID}/attack", json=body)
    finally:
        client.close()
