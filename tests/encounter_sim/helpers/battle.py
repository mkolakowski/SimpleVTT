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
    """Returns an ALREADY-OPEN logged-in GM client. See ``_login_client``."""
    return _login_client("demo-gm@example.com", "demopass")


def _login_client(email: str, password: str) -> httpx.Client:
    """Returns an ALREADY-OPEN logged-in client. Callers must call
    ``.close()`` (or use a try/finally) — do NOT wrap in ``with`` because
    the login call has already implicitly opened the client and httpx's
    context manager rejects a second open.

    Generalized in v2.49.23 so tests that exercise non-GM gates (e.g.
    strict_action_economy) can post as Alice without duplicating the
    login boilerplate. Most helpers default to GM via ``_gm_client``.
    """
    client = httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0)
    resp = client.post("/login", data={"email": email, "password": password})
    if resp.status_code not in (200, 303):
        client.close()
        raise AssertionError(f"{email} login failed: {resp.status_code}")
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


def list_tokens() -> list[dict]:
    """GET ``/api/campaign/{cid}/tokens``. Returns each token's
    ``{id, label, x, y, size, color, image_url, character_id,
    token_template_id, controller_user_id, is_hidden}``.
    """
    client = _gm_client()
    try:
        resp = client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")
        resp.raise_for_status()
        return resp.json().get("tokens", [])
    finally:
        client.close()


def find_token_for_character(character_id: int) -> dict | None:
    """Return the demo token bound to ``character_id``, or None when
    no matching token is on the active map. Convenience for canvas
    pixel-sample tests that need the token's screen position.
    """
    for t in list_tokens():
        if t.get("character_id") == character_id:
            return t
    return None


def bandit_template_id() -> int:
    """Return the demo's Bandit template ID. NPC targets in save-spell
    tests need a real ``token_template_id`` so the server can look up
    the bandit's save modifier from the template; a synthetic combatant
    with no template_id falls through to ``auto_save_target_kind=""``
    and the save isn't rolled. Looked up by name (case-insensitive
    contains 'bandit') so a demo seed reshuffle doesn't break tests.
    """
    client = _gm_client()
    try:
        resp = client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
        resp.raise_for_status()
        templates = resp.json()
        for t in templates:
            if "bandit" in (t.get("name") or "").lower():
                return int(t["id"])
        raise AssertionError(
            f"No bandit template found in /templates ({len(templates)} entries)"
        )
    finally:
        client.close()


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


_DEFAULT_SETTINGS_FORM = {
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


def _post_settings(form_overrides: dict) -> None:
    """POST the full settings form with the given overrides. The
    endpoint expects every field; missing ones null out their column,
    so this helper always sends the demo defaults plus the test's
    overrides. Internal helper — tests call ``set_auto_apply`` or
    ``set_strict_action_economy``.
    """
    form = dict(_DEFAULT_SETTINGS_FORM)
    form.update(form_overrides)
    client = _gm_client()
    try:
        resp = client.post(
            f"/campaign/{CAMPAIGN_ID}/settings",
            data=form,
            follow_redirects=False,
        )
        if resp.status_code not in (200, 303):
            raise AssertionError(
                f"settings POST failed: {resp.status_code} {resp.text}"
            )
    finally:
        client.close()


def set_auto_apply(on: bool, *, strict: bool = False) -> None:
    """Toggle the campaign's ``auto_apply_damage`` setting via the
    settings-form POST so attacks on hit produce a non-zero
    ``damage_applied`` and the bandit's HP actually drops in the
    init tracker. ``strict`` lets callers preserve the strict-action-
    economy state in the same POST (the settings endpoint clears
    omitted checkboxes).
    """
    overrides: dict = {}
    if on:
        overrides["auto_apply_damage"] = "on"
    if strict:
        overrides["strict_action_economy"] = "on"
    _post_settings(overrides)


def set_strict_action_economy(on: bool, *, auto_apply: bool = False) -> None:
    """Toggle ``strict_action_economy``. When True, non-GM players
    cannot bypass the over-budget gate even with ``override=True`` —
    the response is 409 with ``strict: true``. Used by
    ``test_action_economy_strict_mode`` to validate the gate; tests
    that don't need it leave the setting OFF (the demo default).

    Pass ``auto_apply=True`` to preserve the auto-apply-damage state
    in the same POST (since the settings endpoint clears omitted
    checkboxes).
    """
    overrides: dict = {}
    if on:
        overrides["strict_action_economy"] = "on"
    if auto_apply:
        overrides["auto_apply_damage"] = "on"
    _post_settings(overrides)


def cast_spell(
    character_id: int,
    spell_index: int,
    *,
    slot_level: int = 0,
    class_slug: str = "cleric",
    target_combatant_id: str | None = None,
    target_combatant_ids: list[str] | None = None,
    target_name: str | None = None,
    override: bool = True,
) -> httpx.Response:
    """POST ``/cast_spell`` as the GM. Mirrors ``post_attack`` for
    spells: single-target ``target_combatant_id`` for save cantrips
    (Sacred Flame), or multi-target ``target_combatant_ids`` for AoE
    save spells (Fireball).
    """
    body: dict = {
        "character_id": character_id,
        "spell_index": spell_index,
        "slot_level": slot_level,
        "class_slug": class_slug,
        "override": override,
    }
    if target_combatant_id:
        body["target_combatant_id"] = target_combatant_id
    if target_combatant_ids:
        body["target_combatant_ids"] = target_combatant_ids
    if target_name:
        body["target_name"] = target_name
    client = _gm_client()
    try:
        return client.post(f"/api/campaign/{CAMPAIGN_ID}/cast_spell", json=body)
    finally:
        client.close()


def post_attack(
    character_id: int,
    attack_index: int,
    *,
    target_combatant_id: str | None = None,
    bonus_damage: str | None = None,
    bonus_damage_label: str | None = None,
    spend_spell_slot: dict | None = None,
    override: bool = True,
) -> httpx.Response:
    """POST ``/attack`` as the GM. Wraps the call so tests don't
    re-create a logged-in client each time. ``override=True`` bypasses
    the Phase 4 action-economy gate (per CLAUDE.md harness-test rules).

    Uplift parameters (all optional, pass together):
      ``bonus_damage`` + ``bonus_damage_label`` + ``spend_spell_slot``
      drive the Divine Smite / Hex / Sneak Attack / etc. uplifts.
      ``spend_spell_slot`` shape: ``{"class_slug": "paladin", "level": 1}``.
    """
    body: dict = {
        "character_id": character_id,
        "attack_index": attack_index,
        "override": override,
    }
    if target_combatant_id:
        body["target_combatant_id"] = target_combatant_id
    if bonus_damage is not None:
        body["bonus_damage"] = bonus_damage
    if bonus_damage_label is not None:
        body["bonus_damage_label"] = bonus_damage_label
    if spend_spell_slot is not None:
        body["spend_spell_slot"] = spend_spell_slot
    client = _gm_client()
    try:
        return client.post(f"/api/campaign/{CAMPAIGN_ID}/attack", json=body)
    finally:
        client.close()


def post_attack_as_player(
    email: str,
    password: str,
    character_id: int,
    attack_index: int,
    *,
    target_combatant_id: str | None = None,
    override: bool = True,
) -> httpx.Response:
    """POST /attack as a non-GM player. Same shape as ``post_attack``
    but logged in as a specific demo player (e.g.
    ``"demo-alice@example.com"``). Used by
    ``test_action_economy_strict_mode`` to validate the gate: GM
    actions bypass the over-budget gate entirely, so a strict-mode
    test must drive from a player session.
    """
    body: dict = {
        "character_id": character_id,
        "attack_index": attack_index,
        "override": override,
    }
    if target_combatant_id:
        body["target_combatant_id"] = target_combatant_id
    client = _login_client(email, password)
    try:
        return client.post(f"/api/campaign/{CAMPAIGN_ID}/attack", json=body)
    finally:
        client.close()


def death_save_override(
    character_id: int,
    *,
    status: str | None = None,
    successes: int | None = None,
    failures: int | None = None,
) -> httpx.Response:
    """POST ``/character/{cid}/death-save/override`` as the GM —
    force-sets the death-save state without rolling. ``status`` is one
    of "alive" / "dying" / "stable" / "dead". Omitted fields are left
    alone. Broadcasts ``character_death_save`` so connected clients
    update their trackers in place.
    """
    body: dict = {}
    if status is not None:
        body["status"] = status
    if successes is not None:
        body["successes"] = successes
    if failures is not None:
        body["failures"] = failures
    client = _gm_client()
    try:
        return client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{character_id}/death-save/override",
            json=body,
        )
    finally:
        client.close()


def end_concentration(character_id: int) -> httpx.Response:
    """DELETE ``/api/campaign/{cid}/concentration/{char_id}``. Drops
    the caster's concentration effect AND the paired buffs (Hex,
    Hunter's Mark, etc.). Broadcasts ``concentration_update`` with
    ``ended: True`` + ``buff_update`` for the dropped buffs.
    """
    client = _gm_client()
    try:
        return client.delete(f"/api/campaign/{CAMPAIGN_ID}/concentration/{character_id}")
    finally:
        client.close()


def post_use(
    endpoint: str,
    character_id: int,
    *,
    override: bool = True,
    extra: dict | None = None,
) -> httpx.Response:
    """POST a ``/use_X`` feature endpoint (use_rage, use_action_surge,
    use_arcane_recovery, use_lay_on_hands, etc.) as the GM. ``endpoint``
    is the suffix after ``/api/campaign/{cid}/`` (e.g. ``"use_rage"``).
    ``extra`` merges additional body fields when the endpoint needs them
    (e.g. ``{"target_character_id": x}`` for Lay on Hands).
    """
    body: dict = {"character_id": character_id, "override": override}
    if extra:
        body.update(extra)
    client = _gm_client()
    try:
        return client.post(f"/api/campaign/{CAMPAIGN_ID}/{endpoint}", json=body)
    finally:
        client.close()
