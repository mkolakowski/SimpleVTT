"""v2.404.4 — Longstrider multi-target cap + per-slot upcast scaling.

RAW PHB p.255: "You touch a creature. The target's speed increases by 10
feet until the spell ends." Higher Levels: "When you cast this spell using
a spell slot of 2nd level or higher, you can target one additional
creature for each spell slot above 1st."

The v2.404.4 `_SPELL_BUFF_MAP["longstrider"]` entry adds:
  - `max_targets: 1`             (RAW base cap at L1)
  - `base_level: 1`              (the slot level the cap applies at)
  - `extra_targets_per_slot_above_base: 1`  (cap grows +1/slot above base)

Closes the v2.404.x spell utility-upcast arc. First non-concentration
spell in the arc (concentration: False). Same L1-base + extras shape as
Bless, but with `max_targets: 1` (Longstrider's RAW base) instead of 3.
Mira Greenleaf (Druid Lv 6) is the cast surface; her L1 + L2 slots cover
both base cap and +1 upcast extension.

Tests:
  - L1 Longstrider with 1 target → 200 (base cap).
  - L1 Longstrider with 2 targets → 400 too_many_targets, limit=1.
  - L2 Longstrider with 2 targets → 200 (extended cap = 2).
  - L2 Longstrider with 3 targets → 400 too_many_targets, limit=2.
"""
from __future__ import annotations

import pytest_asyncio

from .conftest import CAMPAIGN_ID


# Mira Greenleaf's spell list (app/demo_seed.py:~3179-3191):
# Longstrider is appended at the END (after Conjure Animals at 10) → index 11.
# The full ordering:
#   0 Druidcraft, 1 Produce Flame, 2 Shillelagh,
#   3 Healing Word, 4 Cure Wounds, 5 Faerie Fire,
#   6 Moonbeam, 7 Pass Without Trace, 8 Heat Metal,
#   9 Call Lightning, 10 Conjure Animals, 11 Longstrider ← new.
MIRA_LONGSTRIDER_INDEX = 11


async def _long_rest(gm_client, char_id):
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )


def _mkc(cid, char_id=None, name="X"):
    return {
        "id": cid, "char_id": char_id, "name": name,
        "initiative": 10, "hp_current": 30, "hp_max": 40,
        "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _end_longstrider(gm_client, char_id):
    """Drop any pre-existing Longstrider buff on the target so the cast
    can install fresh. Longstrider is NOT concentration (`concentration:
    False`), so the same-target re-cast would otherwise stack rather than
    swap — `/end_buff` ensures a clean slate."""
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": char_id, "key": "longstrider"},
    )


async def _seed_battle(gm_client, mira, targets):
    """Seed a battle with Mira + N PC targets. Returns target combatant
    id list in placement order."""
    combatants = [_mkc(
        f"tok_lst_mira_{mira['id']}", mira["id"],
        name=mira["name"],
    )]
    target_toks = []
    for i, t in enumerate(targets):
        tok = f"tok_lst_{t['id']}_{i}"
        combatants.append(_mkc(tok, t["id"], name=t["name"]))
        target_toks.append(tok)
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )
    return target_toks


@pytest_asyncio.fixture
async def mira(gm_client, roster):
    mira = roster["Mira Greenleaf"]
    await _long_rest(gm_client, mira["id"])
    return mira


@pytest_asyncio.fixture
async def one_target(gm_client, roster):
    pc = roster["Pip Quickfingers"]
    await _end_longstrider(gm_client, pc["id"])
    return [pc]


@pytest_asyncio.fixture
async def two_targets(gm_client, one_target, roster):
    pc = roster["Krieger Stonefist"]
    await _end_longstrider(gm_client, pc["id"])
    return one_target + [pc]


@pytest_asyncio.fixture
async def three_targets(gm_client, two_targets, roster):
    pc = roster["Kael Brightleaf"]
    await _end_longstrider(gm_client, pc["id"])
    return two_targets + [pc]


async def test_longstrider_l1_one_target_succeeds(
    gm_client, mira, one_target,
):
    """L1 Longstrider with 1 target → 200 (RAW base cap)."""
    toks = await _seed_battle(gm_client, mira, one_target)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": mira["id"],
            "spell_index": MIRA_LONGSTRIDER_INDEX,
            "slot_level": 1,
            "class_slug": "druid",
            "target_combatant_ids": toks,
            "target_name": "Longstrider (L1, 1 target)",
            "override": True,
            "override_range": True,
        },
    )
    assert resp.status_code == 200, resp.text
    # Cleanup — drop the installed buff so subsequent tests cast fresh.
    for pc in one_target:
        await _end_longstrider(gm_client, pc["id"])


async def test_longstrider_l1_two_targets_returns_400(
    gm_client, mira, two_targets,
):
    """L1 Longstrider with 2 targets → 400 too_many_targets, limit=1."""
    toks = await _seed_battle(gm_client, mira, two_targets)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": mira["id"],
            "spell_index": MIRA_LONGSTRIDER_INDEX,
            "slot_level": 1,
            "class_slug": "druid",
            "target_combatant_ids": toks,
            "target_name": "Longstrider (L1, 2 targets)",
            "override": True,
            "override_range": True,
        },
    )
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body.get("error") == "too_many_targets"
    assert body.get("limit") == 1
    assert body.get("received") == 2


async def test_longstrider_l2_two_targets_succeeds(
    gm_client, mira, two_targets,
):
    """L2 Longstrider with 2 targets → 200 (extended cap = 1 + (2-1)*1 = 2)."""
    toks = await _seed_battle(gm_client, mira, two_targets)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": mira["id"],
            "spell_index": MIRA_LONGSTRIDER_INDEX,
            "slot_level": 2,
            "class_slug": "druid",
            "target_combatant_ids": toks,
            "target_name": "Longstrider (L2, 2 targets)",
            "override": True,
            "override_range": True,
        },
    )
    assert resp.status_code == 200, resp.text
    # Cleanup.
    for pc in two_targets:
        await _end_longstrider(gm_client, pc["id"])


async def test_longstrider_l2_three_targets_returns_400(
    gm_client, mira, three_targets,
):
    """L2 Longstrider with 3 targets → 400 too_many_targets, limit=2 (the
    extended cap, not the base 1)."""
    toks = await _seed_battle(gm_client, mira, three_targets)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": mira["id"],
            "spell_index": MIRA_LONGSTRIDER_INDEX,
            "slot_level": 2,
            "class_slug": "druid",
            "target_combatant_ids": toks,
            "target_name": "Longstrider (L2, 3 targets)",
            "override": True,
            "override_range": True,
        },
    )
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body.get("error") == "too_many_targets"
    # Confirms the upcast field is honored — limit is 2, not 1.
    assert body.get("limit") == 2
    assert body.get("received") == 3
