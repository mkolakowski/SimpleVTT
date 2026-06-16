"""v2.359.0 — magic-items: Staff of the Magi (RAW DMG p.202, legendary,
attunement by a sorcerer/warlock/wizard). Bucket-B passive drop-in
reusing the v2.358.0 `spell_dc_bonus` substrate: "+2 bonus to spell
attack rolls and spell saving throw DCs." v1 wires the **+2 spell save
DC** (folded into `_compute_spell_save_dc_from_sheet`); the +2 spell
attack bonus, the 50-charge spell list, spell absorption, and retributive
strike are GM-narrated.

Observability: Thalindra Moonwhisper (Evocation Wizard) carries the staff
as inert Armory's Remainder loot and knows Fireball (DEX save). Casting
Fireball at an NPC bandit returns `auto_save_dc` = her spell save DC, so
the +2 shows as a delta between the staff-attuned cast and the
staff-inert cast (seed-inert + PATCH-in-test; long rest refreshes the
slot between the two casts).

Tests:
  - Fireball's `auto_save_dc` is exactly 2 higher with the staff
    equipped+attuned than with it inert.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_MAGI = "staff-of-the-magi"


def _slug_index(inventory, slug):
    for i, it in enumerate(inventory):
        if isinstance(it, dict) and (it.get("_slug") or "") == slug:
            return i
    return -1


async def _sheet(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    return (r.json() or {}).get("sheet") or {}


async def _patch(gm_client, char_id, fields):
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json=fields,
    )


async def _long_rest(gm_client, char_id):
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )


async def _bandit_template_id(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    assert r.status_code == 200, r.text
    b = next((t for t in r.json() if "bandit" in (t.get("name") or "").lower()), None)
    assert b is not None, "Bandit template missing from the demo seed"
    return b["id"]


async def _fireball_index(gm_client, char_id):
    sheet = await _sheet(gm_client, char_id)
    for i, sp in enumerate(sheet.get("spells") or []):
        if isinstance(sp, dict) and sp.get("_slug") == "fireball":
            return i
    raise AssertionError("Thalindra has no Fireball in her spell list")


def _set_magi(inv, *, equipped, attuned):
    new_inv = [dict(it) if isinstance(it, dict) else it for it in inv]
    found = False
    for it in new_inv:
        if isinstance(it, dict) and it.get("_slug") == _MAGI:
            it["equipped"], it["attuned"] = equipped, attuned
            found = True
    assert found, "Thalindra has no staff-of-the-magi item"
    return new_inv


@pytest_asyncio.fixture
async def thalindra(roster):
    return roster["Thalindra Moonwhisper"]


async def _cast_fireball_dc(gm_client, thalindra, sp_idx, template_id, tag):
    bandit = f"tok_sotm_{tag}"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_sotm_th_{thalindra['id']}_{tag}", "char_id": thalindra["id"],
             "name": thalindra["name"], "initiative": 10,
             "hp_current": 30, "hp_max": 30, "buffs": [],
             "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
            {"id": bandit, "char_id": None, "token_template_id": template_id,
             "name": "Bandit", "initiative": 7, "hp_current": 50, "hp_max": 50,
             "buffs": [],
             "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thalindra["id"],
            "spell_index": sp_idx,
            "slot_level": 3,
            "class_slug": "wizard",
            "target_combatant_id": bandit,
            "target_name": "Bandit",
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    return int(resp.json().get("auto_save_dc") or 0)


async def test_magi_boosts_spell_save_dc(gm_client, thalindra):
    """Fireball's auto_save_dc is exactly +2 with the Staff of the Magi
    equipped+attuned vs inert — proving the `spell_dc_bonus` passive."""
    template_id = await _bandit_template_id(gm_client)
    sheet = await _sheet(gm_client, thalindra["id"])
    inv = list(sheet.get("inventory") or [])
    inv_snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    sp_idx = await _fireball_index(gm_client, thalindra["id"])
    try:
        # Baseline: staff inert.
        await _patch(gm_client, thalindra["id"],
                     {"inventory": _set_magi(inv, equipped=False, attuned=False)})
        await _long_rest(gm_client, thalindra["id"])
        dc_base = await _cast_fireball_dc(
            gm_client, thalindra, sp_idx, template_id, "base")

        # Boosted: staff equipped+attuned.
        await _patch(gm_client, thalindra["id"],
                     {"inventory": _set_magi(inv, equipped=True, attuned=True)})
        await _long_rest(gm_client, thalindra["id"])
        dc_boost = await _cast_fireball_dc(
            gm_client, thalindra, sp_idx, template_id, "boost")

        assert dc_base > 0 and dc_boost > 0, (dc_base, dc_boost)
        assert dc_boost - dc_base == 2, (
            f"Staff of the Magi should add +2 to the spell save DC; "
            f"base={dc_base} boost={dc_boost}"
        )
    finally:
        await _patch(gm_client, thalindra["id"], {"inventory": inv_snapshot})
        await _long_rest(gm_client, thalindra["id"])
