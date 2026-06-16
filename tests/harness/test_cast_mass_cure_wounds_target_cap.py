"""v2.381.1 — Mass Cure Wounds multi-target cap (RAW PHB p.258: "up to
six creatures"). Mirror of the v2.381.0 Mass Healing Word tests for
the second entry already wired in `_SPELL_TARGET_CAPS`.

Mass Cure Wounds is L5 (vs Mass Healing Word's L3) and Tavik (Cleric
Lv 8) doesn't have it on his spell list natively + doesn't have L5
slots, so the test PATCHes both:
- adds Mass Cure Wounds to his spell list (index = 13, the new tail);
- PATCHes a temp L5 cleric slot;
- restores both in a `finally` clause so the demo seed is unchanged.

The cap math is identical to v2.381.0 — `max_targets: 6, base_level: 5`
with no `extra_targets_per_slot_above_base`, so the count stays 6
across upcasts. RAW: healing dice scale (+1d8 per slot above 5th),
target count fixed.

Tests:
  - L5 Mass Cure Wounds with 6 targets → 200 (base cap).
  - L5 with 7 targets → 400 too_many_targets, limit=6.
  - L6 with 7 targets → 400 (cap stays fixed; upcast doesn't extend).
"""
from __future__ import annotations

import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _mkc(cid, char_id=None, name="X"):
    return {
        "id": cid, "char_id": char_id, "name": name,
        "initiative": 10, "hp_current": 30, "hp_max": 40,
        "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _long_rest(gm_client, char_id):
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )


async def _patch_spells_and_slot(gm_client, char_id):
    """PATCH Tavik to add Mass Cure Wounds + a temp L5 cleric slot.
    Returns (original spells list, original spell_slots dict) for
    restore. The new spell goes at the tail of Tavik's list (index 13,
    one past the existing Mass Healing Word at 12)."""
    sheet_r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    sheet = (sheet_r.json() or {}).get("sheet") or {}
    orig_spells = list(sheet.get("spells") or [])
    orig_slots = dict(sheet.get("spell_slots") or {})
    new_spells = list(orig_spells) + [
        {
            "name": "Mass Cure Wounds",
            "level": 5,
            "prepared": True,
            "_slug": "mass-cure-wounds",
            "casting_time": "1 action",
        },
    ]
    new_slots = {**orig_slots}
    new_slots["cleric"] = dict(new_slots.get("cleric") or {})
    new_slots["cleric"]["5"] = {"total": 1, "used": 0}
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"spells": new_spells, "spell_slots": new_slots},
    )
    return orig_spells, orig_slots, len(orig_spells)  # new spell index = len(orig)


async def _restore_spells_and_slots(gm_client, char_id, spells, slots):
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"spells": spells, "spell_slots": slots},
    )


async def _seed_battle(gm_client, tavik, targets):
    combatants = [_mkc(
        f"tok_mcw_tavik_{tavik['id']}", tavik["id"], name=tavik["name"],
    )]
    target_toks = []
    for i, t in enumerate(targets):
        tok = f"tok_mcw_{t['id']}_{i}"
        combatants.append(_mkc(tok, t["id"], name=t["name"]))
        target_toks.append(tok)
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )
    return target_toks


@pytest_asyncio.fixture
async def tavik(gm_client, roster):
    tavik = roster["Brother Tavik Stonebrow"]
    await _long_rest(gm_client, tavik["id"])
    return tavik


@pytest_asyncio.fixture
async def six_targets(gm_client, roster):
    return [
        roster["Pip Quickfingers"],
        roster["Thalindra Moonwhisper"],
        roster["Sir Caelan Lightbringer"],
        roster["Mira Greenleaf"],
        roster["Kael Brightleaf"],
        roster["Krieger Stonefist"],
    ]


@pytest_asyncio.fixture
async def seven_targets(gm_client, six_targets, roster):
    return six_targets + [roster["Garrik Ironside"]]


async def test_mass_cure_wounds_l5_six_targets_succeeds(
    gm_client, tavik, six_targets,
):
    """L5 Mass Cure Wounds with 6 targets → 200 (RAW base cap)."""
    orig_spells, orig_slots, mcw_index = await _patch_spells_and_slot(
        gm_client, tavik["id"],
    )
    try:
        toks = await _seed_battle(gm_client, tavik, six_targets)
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": tavik["id"],
                "spell_index": mcw_index,
                "slot_level": 5,
                "class_slug": "cleric",
                "target_combatant_ids": toks,
                "target_name": "Mass Cure Wounds (6 targets)",
                "override": True,
                "override_range": True,
            },
        )
        assert resp.status_code == 200, resp.text
    finally:
        await _restore_spells_and_slots(
            gm_client, tavik["id"], orig_spells, orig_slots,
        )


async def test_mass_cure_wounds_l5_seven_targets_returns_400(
    gm_client, tavik, seven_targets,
):
    """L5 Mass Cure Wounds with 7 targets → 400 too_many_targets, limit=6."""
    orig_spells, orig_slots, mcw_index = await _patch_spells_and_slot(
        gm_client, tavik["id"],
    )
    try:
        toks = await _seed_battle(gm_client, tavik, seven_targets)
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": tavik["id"],
                "spell_index": mcw_index,
                "slot_level": 5,
                "class_slug": "cleric",
                "target_combatant_ids": toks,
                "target_name": "Mass Cure Wounds (7 targets)",
                "override": True,
                "override_range": True,
            },
        )
        assert resp.status_code == 400, resp.text
        body = resp.json()
        assert body.get("error") == "too_many_targets"
        assert body.get("spell") == "mass-cure-wounds"
        assert body.get("limit") == 6
        assert body.get("received") == 7
    finally:
        await _restore_spells_and_slots(
            gm_client, tavik["id"], orig_spells, orig_slots,
        )


async def test_mass_cure_wounds_l6_seven_targets_still_400(
    gm_client, tavik, seven_targets,
):
    """L6 Mass Cure Wounds with 7 targets → 400 (cap stays fixed at 6;
    upcast scales healing dice, not target count)."""
    orig_spells, orig_slots, mcw_index = await _patch_spells_and_slot(
        gm_client, tavik["id"],
    )
    try:
        toks = await _seed_battle(gm_client, tavik, seven_targets)
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": tavik["id"],
                "spell_index": mcw_index,
                "slot_level": 6,
                "class_slug": "cleric",
                "target_combatant_ids": toks,
                "target_name": "Mass Cure Wounds (L6, 7 targets)",
                "override": True,
                "override_range": True,
            },
        )
        assert resp.status_code == 400, resp.text
        body = resp.json()
        assert body.get("limit") == 6
    finally:
        await _restore_spells_and_slots(
            gm_client, tavik["id"], orig_spells, orig_slots,
        )
