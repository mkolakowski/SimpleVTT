"""v2.958.0 — the ``enforce_gm_ranges`` campaign toggle holds the GM to the
same weapon/spell RANGE gate players get.

By default the GM is the rules authority and auto-bypasses ``_check_cast_range``
(Tier 1), so a GM-driven out-of-range attack silently succeeds. This is the
exact limitation ``test_cast_attack_range.py`` documents ("GM auto-bypasses the
range check… A future commit could add ownership-swap fixtures"). With the
toggle ON, the GM falls through to the distance check and gets the same 409
``out_of_range`` — but can still override (the GM's override always clears,
regardless of strict mode).

Coverage:
  - toggle OFF (demo default): GM out-of-range attack → 200 (bypass intact).
  - toggle ON: GM out-of-range attack → 409 ``out_of_range``.
  - toggle ON + ``override_range: true``: → 200 (GM override clears the gate).
  - toggle ON, in-range: → 200 (the gate only bites out of range).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

PX_PER_CELL = 70


# --- settings form -------------------------------------------------------

def _settings_form(*, enforce_gm_ranges: bool) -> dict:
    """Full settings form. Omitting a checkbox key = the server reads it as
    False, so every preserved toggle must be echoed. auto_apply_damage stays
    "on" to keep the demo seed's default (see test_attack_auto_damage.py)."""
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
        "auto_apply_damage": "on",
    }
    if enforce_gm_ranges:
        form["enforce_gm_ranges"] = "on"
    return form


async def _set_enforce(gm_client, on: bool) -> None:
    await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings",
        data=_settings_form(enforce_gm_ranges=on),
        follow_redirects=False,
    )


@pytest_asyncio.fixture
async def restore_enforce(gm_client):
    """Guarantee the toggle is OFF again after the test (demo default)."""
    yield
    await _set_enforce(gm_client, False)


# --- token / battle helpers (mirror test_cast_attack_range.py) -----------

async def _bandit_template(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    return next((t for t in templates if t["name"].lower() == "bandit"), templates[0])


async def _ensure_pc_token(gm_client, char_id: int, x: float, y: float) -> dict:
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")
    by_char = {t.get("character_id"): t for t in r.json()["tokens"] if t.get("character_id")}
    tok = by_char.get(char_id)
    if not tok:
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/place-token",
            json={"x": x, "y": y})
        r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")
        by_char = {t.get("character_id"): t for t in r.json()["tokens"] if t.get("character_id")}
        tok = by_char[char_id]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{tok['id']}/move", json={"x": x, "y": y})
    return tok


async def _place_test_npc(gm_client, x: float, y: float, tmpl_id: int, label: str) -> dict:
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/tokens",
        json={"token_template_id": tmpl_id, "x": x, "y": y, "label": label, "color": "#cc3333"})
    assert r.status_code == 200, r.text
    return r.json()


async def _seed_battle(gm_client, caster, bandit_token, bandit_tmpl, prefix):
    combatant_id = f"{prefix}_{bandit_token['id']}"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"{prefix}_c_{caster['id']}", "char_id": caster["id"],
             "name": caster["name"], "initiative": 10, "hp_current": 30, "hp_max": 30,
             "buffs": [], "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
            {"id": combatant_id, "char_id": None, "token_template_id": bandit_tmpl["id"],
             "source_token_id": bandit_token["id"], "name": bandit_token.get("label") or "Bandit",
             "initiative": 5, "hp_current": 11, "hp_max": 11, "buffs": [],
             "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True})
    return combatant_id


async def _gm_attacks(gm_client, pip, combatant_id, *, override_range=False):
    body = {"character_id": pip["id"], "attack_index": 0,  # Shortsword (5 ft)
            "target_combatant_id": combatant_id, "override": True}
    if override_range:
        body["override_range"] = True
    return await gm_client.post(f"/api/campaign/{CAMPAIGN_ID}/attack", json=body)


# --- tests ---------------------------------------------------------------

async def test_gm_bypass_when_toggle_off(gm_client, roster, restore_enforce):
    """Toggle OFF (demo default): the GM's out-of-range shortsword still lands
    (rules-authority bypass)."""
    await _set_enforce(gm_client, False)
    pip = roster["Pip Quickfingers"]
    tmpl = await _bandit_template(gm_client)
    await _ensure_pc_token(gm_client, pip["id"], 100, 100)
    bandit = await _place_test_npc(gm_client, 100 + 10 * PX_PER_CELL, 100, tmpl["id"], "GMRange off")
    try:
        cid = await _seed_battle(gm_client, pip, bandit, tmpl, "tok_gmr_off")
        r = await _gm_attacks(gm_client, pip, cid)
        assert r.status_code == 200, r.text
    finally:
        await gm_client.delete(f"/api/campaign/{CAMPAIGN_ID}/tokens/{bandit['id']}")


async def test_gm_blocked_when_toggle_on(gm_client, roster, restore_enforce):
    """Toggle ON: the GM's out-of-range shortsword (5 ft) at a bandit 50 ft
    away returns the same 409 ``out_of_range`` players get."""
    await _set_enforce(gm_client, True)
    pip = roster["Pip Quickfingers"]
    tmpl = await _bandit_template(gm_client)
    await _ensure_pc_token(gm_client, pip["id"], 100, 100)
    bandit = await _place_test_npc(gm_client, 100 + 10 * PX_PER_CELL, 100, tmpl["id"], "GMRange on")
    try:
        cid = await _seed_battle(gm_client, pip, bandit, tmpl, "tok_gmr_on")
        r = await _gm_attacks(gm_client, pip, cid)
        assert r.status_code == 409, r.text
        err = r.json()
        assert err["error"] == "out_of_range", err
        assert err["range_ft"] == 5, err
        assert err["distance_ft"] == 50.0, err
    finally:
        await gm_client.delete(f"/api/campaign/{CAMPAIGN_ID}/tokens/{bandit['id']}")


async def test_gm_override_clears_gate(gm_client, roster, restore_enforce):
    """Toggle ON + ``override_range: true``: the GM narrates past the gate → 200.
    The GM's override clears unconditionally (rules authority)."""
    await _set_enforce(gm_client, True)
    pip = roster["Pip Quickfingers"]
    tmpl = await _bandit_template(gm_client)
    await _ensure_pc_token(gm_client, pip["id"], 100, 100)
    bandit = await _place_test_npc(gm_client, 100 + 10 * PX_PER_CELL, 100, tmpl["id"], "GMRange ovr")
    try:
        cid = await _seed_battle(gm_client, pip, bandit, tmpl, "tok_gmr_ovr")
        r = await _gm_attacks(gm_client, pip, cid, override_range=True)
        assert r.status_code == 200, r.text
    finally:
        await gm_client.delete(f"/api/campaign/{CAMPAIGN_ID}/tokens/{bandit['id']}")


async def test_gm_in_range_unaffected(gm_client, roster, restore_enforce):
    """Toggle ON, target ~5 ft away: the gate only bites out of range → 200."""
    await _set_enforce(gm_client, True)
    pip = roster["Pip Quickfingers"]
    tmpl = await _bandit_template(gm_client)
    await _ensure_pc_token(gm_client, pip["id"], 100, 100)
    bandit = await _place_test_npc(gm_client, 100 + PX_PER_CELL, 100, tmpl["id"], "GMRange near")
    try:
        cid = await _seed_battle(gm_client, pip, bandit, tmpl, "tok_gmr_near")
        r = await _gm_attacks(gm_client, pip, cid)
        assert r.status_code == 200, r.text
    finally:
        await gm_client.delete(f"/api/campaign/{CAMPAIGN_ID}/tokens/{bandit['id']}")
