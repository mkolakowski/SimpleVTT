"""v2.397.0 — Hill Dwarf heavy-armor speed bypass (race-features
plan Phase 3).

RAW PHB p.144 Heavy Armor table: when the wearer's STR is below the
armor's STR requirement, walking speed is reduced by 10. RAW PHB
p.20 Dwarf: "Your speed is not reduced by wearing heavy armor."

New `_pc_heavy_armor_speed_penalty(sheet)` predicate returns 0 for
Dwarves regardless of STR, and 10 for non-Dwarves whose STR is
below the equipped heavy armor's `_HEAVY_ARMOR_STR_REQ` value
(chain-mail 13 / splint 15 / plate 15). `_speed_walk_from_sheet`
subtracts the penalty from the returned speed; `/sheet-json`
surfaces a `derived.heavy_armor_speed_penalty: {penalty_ft, source}`
block when the penalty fires so harness / chat-card / UI can
attribute the -10.

Test strategy (4 tests):
1. Tavik (Hill Dwarf, STR 14) in chain mail (STR req 13) — no
   penalty fires (STR ≥ req regardless of race). `derived`
   has no `heavy_armor_speed_penalty` key.
2. Tavik PATCHed into a fake plate item (STR req 15) — STILL no
   penalty (RAW Dwarf exemption). Verifies the race-exemption gate.
3. Tavik PATCHed to race "Human" + plate — penalty 10 fires.
   Verifies the gate's non-Dwarf branch.
4. Restore Tavik's race + inventory at the end so downstream
   tests aren't polluted. (Pytest fixture-style teardown via
   try/finally inside each test.)
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def tavik_rested(gm_client, roster):
    tavik = roster["Brother Tavik Stonebrow"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/rest",
        json={"type": "long"},
    )
    return tavik


async def _get_sheet(gm_client, char_id: int) -> dict:
    snap = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    body = snap.json() or {}
    return body


async def test_dwarf_in_chain_mail_no_penalty(gm_client, tavik_rested):
    """Tavik (Hill Dwarf, STR 14) wears chain mail (STR req 13). STR
    ≥ req, so no penalty even without the race exemption. The
    Dwarf-exemption gate fires first, but the same answer (no
    penalty) results."""
    tavik = tavik_rested
    body = await _get_sheet(gm_client, tavik["id"])
    derived = body.get("derived") or {}
    assert "heavy_armor_speed_penalty" not in derived, (
        f"Tavik in chain mail (STR 14 ≥ 13) should have no penalty; "
        f"got derived.heavy_armor_speed_penalty = "
        f"{derived.get('heavy_armor_speed_penalty')!r}"
    )


async def test_dwarf_in_plate_no_penalty_via_race_exemption(
    gm_client, tavik_rested,
):
    """Tavik (Hill Dwarf, STR 14) PATCHed into plate (STR req 15).
    Without the race exemption STR 14 < 15 would fire the -10
    penalty; the Dwarf exemption suppresses it. Validates the
    race-gate's first branch."""
    tavik = tavik_rested
    # Snapshot the original inventory so we can restore at the end.
    snap = await _get_sheet(gm_client, tavik["id"])
    orig_inventory = list((snap.get("sheet") or {}).get("inventory") or [])
    # Swap Tavik's chain mail for plate.
    new_inventory = []
    for it in orig_inventory:
        if isinstance(it, dict) and (it.get("_slug") or "") == "chain-mail":
            updated = dict(it)
            updated["_slug"] = "plate"
            updated["name"] = "Plate"
            updated["ac_value"] = 18
            new_inventory.append(updated)
        else:
            new_inventory.append(it)
    try:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/sheet-fields",
            json={"inventory": new_inventory},
        )
        body = await _get_sheet(gm_client, tavik["id"])
        derived = body.get("derived") or {}
        assert "heavy_armor_speed_penalty" not in derived, (
            f"Dwarf exemption should suppress the plate STR penalty; "
            f"got derived.heavy_armor_speed_penalty = "
            f"{derived.get('heavy_armor_speed_penalty')!r}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/sheet-fields",
            json={"inventory": orig_inventory},
        )


async def test_non_dwarf_in_plate_takes_penalty(gm_client, tavik_rested):
    """Tavik PATCHed to race='Human' + plate (STR req 15). STR 14 <
    15, no race exemption → penalty 10 fires. Validates the
    non-Dwarf branch of the gate."""
    tavik = tavik_rested
    snap = await _get_sheet(gm_client, tavik["id"])
    orig_inventory = list((snap.get("sheet") or {}).get("inventory") or [])
    orig_race = (snap.get("sheet") or {}).get("race") or "Hill Dwarf"
    new_inventory = []
    for it in orig_inventory:
        if isinstance(it, dict) and (it.get("_slug") or "") == "chain-mail":
            updated = dict(it)
            updated["_slug"] = "plate"
            updated["name"] = "Plate"
            updated["ac_value"] = 18
            new_inventory.append(updated)
        else:
            new_inventory.append(it)
    try:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/sheet-fields",
            json={"inventory": new_inventory, "race": "Human"},
        )
        body = await _get_sheet(gm_client, tavik["id"])
        derived = body.get("derived") or {}
        penalty_block = derived.get("heavy_armor_speed_penalty")
        assert penalty_block is not None, (
            f"non-Dwarf wearing plate at STR 14 (< req 15) should take "
            f"the -10 penalty; got derived = {derived}"
        )
        assert int(penalty_block.get("penalty_ft") or 0) == 10, (
            f"expected penalty_ft=10; got {penalty_block}"
        )
        assert "plate" in (penalty_block.get("source") or "").lower(), (
            f"penalty source should mention plate; got {penalty_block}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/sheet-fields",
            json={"inventory": orig_inventory, "race": orig_race},
        )


async def test_non_dwarf_sufficient_str_no_penalty(gm_client, tavik_rested):
    """Control: Tavik PATCHed to race='Human' + plate + STR 15 (meets
    plate's STR req). No penalty fires because STR ≥ req. Verifies
    the STR-threshold half of the gate (not the race exemption
    half)."""
    tavik = tavik_rested
    snap = await _get_sheet(gm_client, tavik["id"])
    sheet = snap.get("sheet") or {}
    orig_inventory = list(sheet.get("inventory") or [])
    orig_race = sheet.get("race") or "Hill Dwarf"
    orig_abilities = dict(sheet.get("abilities") or {})
    new_inventory = []
    for it in orig_inventory:
        if isinstance(it, dict) and (it.get("_slug") or "") == "chain-mail":
            updated = dict(it)
            updated["_slug"] = "plate"
            updated["name"] = "Plate"
            updated["ac_value"] = 18
            new_inventory.append(updated)
        else:
            new_inventory.append(it)
    new_abilities = dict(orig_abilities)
    new_abilities["STR"] = 15
    try:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/sheet-fields",
            json={
                "inventory": new_inventory,
                "race": "Human",
                "abilities": new_abilities,
            },
        )
        body = await _get_sheet(gm_client, tavik["id"])
        derived = body.get("derived") or {}
        assert "heavy_armor_speed_penalty" not in derived, (
            f"non-Dwarf in plate at STR 15 (= req 15) should NOT take "
            f"the -10 penalty; got derived = {derived}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/sheet-fields",
            json={
                "inventory": orig_inventory,
                "race": orig_race,
                "abilities": orig_abilities,
            },
        )
