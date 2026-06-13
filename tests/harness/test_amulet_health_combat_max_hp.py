"""v2.220.0 — the Amulet of Health's boosted max HP now drives the
combat heal-clamp, not just the ``/sheet-json`` display (v2.216.0).

RAW DMG p.150: the amulet sets CON to 19, raising max HP by the
CON-modifier delta × character level. Phase 3 (v2.216.0) surfaced that
as a display-derived ``derived.effective_max_hp`` but left the stored
``hp.max`` (and therefore the combat heal-clamp) untouched — a heal
still capped at the un-boosted max. This commit folds the same
``_effective_max_hp_for_sheet`` delta into ``_apply_heal_to_combatant``'s
ceiling so heals restore up to the boosted pool.

Demo fixture: Brother Tavik Stonebrow (Cleric Lv 8) wears an equipped +
attuned Amulet of Health — stored max HP 67, effective max HP 83 (+16
from CON 14→19, mod +2→+4, ×8 levels).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_AMULET_SLUG = "amulet-of-health"
HEALING_WORD_INDEX = 5  # See test_cast_spell.py for index notes.


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest_asyncio.fixture
async def tavik(roster):
    return roster["Brother Tavik Stonebrow"]


async def _set_hp(gm_client, char_id, current):
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"hp": {"current": current}},
    )


async def _long_rest(gm_client, char_id):
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )


async def _seed_solo_battle(gm_client, char_id, name, hp_current, hp_max):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [{
                "id": f"tok_test_{char_id}",
                "char_id": char_id,
                "name": name,
                "initiative": 10,
                "hp_current": hp_current,
                "hp_max": hp_max,
                "buffs": [],
                "economy": {"action": False, "bonus": False,
                            "reaction": False, "movement": 0},
            }],
            "turn_index": 0, "round": 1, "active": True,
        },
    )


async def _self_heal(gm_client, tavik):
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": tavik["id"],
            "spell_index": HEALING_WORD_INDEX,
            "slot_level": 1,
            "class_slug": "cleric",
            "target_character_id": tavik["id"],
            "target_combatant_id": f"tok_test_{tavik['id']}",
            "target_name": tavik["name"],
            "override": True,
        },
    )


async def test_heal_at_stored_max_uses_amulet_ceiling(gm_client, tavik):
    """Tavik at his stored max self-casts Healing Word. Because the Amulet
    of Health raises the effective ceiling above the stored max, the heal
    lands (applied > 0) and pushes current above the stored max — proof
    the combat heal-clamp now reads the boosted pool, not hp.max."""
    data = await _sheet_json(gm_client, tavik["id"])
    stored_max = int(((data.get("sheet") or {}).get("hp") or {}).get("max") or 0)
    effective = ((data.get("derived") or {}).get("effective_max_hp") or {}).get(
        "effective"
    )
    assert effective and effective > stored_max, (
        f"fixture precondition: amulet should raise the ceiling above "
        f"{stored_max}; got effective_max_hp={effective!r}"
    )
    try:
        await _set_hp(gm_client, tavik["id"], stored_max)
        await _seed_solo_battle(
            gm_client, tavik["id"], tavik["name"], stored_max, stored_max,
        )
        resp = await _self_heal(gm_client, tavik)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["auto_heal_applied"] > 0, (
            f"heal should land past the stored max via the amulet ceiling; "
            f"got applied={body['auto_heal_applied']}"
        )
        hp_after = body["auto_heal_hp_after"]
        assert stored_max < hp_after <= effective, (
            f"expected {stored_max} < hp_after <= {effective}; got {hp_after}"
        )
    finally:
        await _long_rest(gm_client, tavik["id"])


async def test_heal_at_stored_max_caps_without_amulet(gm_client, tavik):
    """Guard: with the amulet unequipped the boost is gone, so a heal at
    the stored max applies 0 (the clamp falls back to hp.max). Proves the
    boosted ceiling is amulet-driven, not unconditional. Restores the
    original inventory + full HP on teardown."""
    data = await _sheet_json(gm_client, tavik["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    stored_max = int(((data.get("sheet") or {}).get("hp") or {}).get("max") or 0)
    idx = next(
        (i for i, it in enumerate(inv)
         if isinstance(it, dict) and it.get("_slug") == _AMULET_SLUG),
        None,
    )
    assert idx is not None, "Tavik has no amulet-of-health item"
    try:
        inv[idx] = {**inv[idx], "equipped": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/sheet-fields",
            json={"inventory": inv},
        )
        await _set_hp(gm_client, tavik["id"], stored_max)
        await _seed_solo_battle(
            gm_client, tavik["id"], tavik["name"], stored_max, stored_max,
        )
        resp = await _self_heal(gm_client, tavik)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["auto_heal_applied"] == 0, (
            f"without the amulet the heal must cap at the stored max; "
            f"got applied={body['auto_heal_applied']}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/sheet-fields",
            json={"inventory": snapshot},
        )
        await _long_rest(gm_client, tavik["id"])
