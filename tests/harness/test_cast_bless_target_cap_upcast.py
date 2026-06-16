"""v2.380.0 — Bless multi-target cap + per-slot upcast scaling.

RAW PHB p.219: "Choose up to three creatures within range." Higher Levels:
"When you cast this spell using a spell slot of 2nd level or higher, you
can target one additional creature for each slot level above 1st."

The v2.380.0 `_SPELL_BUFF_MAP["bless"]` entry gains three new fields:
  - `max_targets: 3`            (RAW base cap at L1)
  - `base_level: 1`             (the slot level the cap applies at)
  - `extra_targets_per_slot_above_base: 1`  (cap grows +1/slot above base)

The /cast_spell `max_targets` gate (v2.372.1 — originally added for Aid)
now reads the upcast field and extends the effective cap by
`(slot_level - base_level) * extra_per_slot`. Aid keeps its hard 3-cap
(no `extra_targets_per_slot_above_base` set) so the existing contract
is preserved for spells that don't scale.

Tests:
  - L1 Bless with 3 targets → 200 (base cap).
  - L1 Bless with 4 targets → 400 too_many_targets, limit=3.
  - L2 Bless with 4 targets → 200 (extended cap = 4).
  - L2 Bless with 5 targets → 400 too_many_targets, limit=4.
"""
from __future__ import annotations

import pytest_asyncio

from .conftest import CAMPAIGN_ID


CAELAN_BLESS_INDEX = 0  # Caelan's spell list (app/demo_seed.py:~1847):
                        # 0 Bless, 1 Cure Wounds, 2 Shield of Faith, ...


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


async def _end_bless(gm_client, char_id):
    """Drop any pre-existing Bless buff on the target so the cast can
    install fresh (the concentration swap rule would otherwise mask
    leftover state from prior tests)."""
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": char_id, "key": "bless"},
    )


async def _end_caelan_concentration(gm_client, caelan_id):
    """Drop Caelan's concentration before each test so the prior Bless
    cast doesn't block re-casting. Bless is concentration."""
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": caelan_id, "key": "bless"},
    )


async def _seed_battle(gm_client, caelan, targets):
    """Seed a battle with Caelan + N PC targets. Returns target combatant
    id list in placement order."""
    combatants = [_mkc(
        f"tok_bless_caelan_{caelan['id']}", caelan["id"],
        name=caelan["name"],
    )]
    target_toks = []
    for i, t in enumerate(targets):
        tok = f"tok_bless_{t['id']}_{i}"
        combatants.append(_mkc(tok, t["id"], name=t["name"]))
        target_toks.append(tok)
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )
    return target_toks


@pytest_asyncio.fixture
async def caelan(gm_client, roster):
    caelan = roster["Sir Caelan Lightbringer"]
    await _long_rest(gm_client, caelan["id"])
    await _end_caelan_concentration(gm_client, caelan["id"])
    return caelan


@pytest_asyncio.fixture
async def three_targets(gm_client, roster):
    pcs = [
        roster["Pip Quickfingers"],
        roster["Krieger Stonefist"],
        roster["Kael Brightleaf"],
    ]
    for pc in pcs:
        await _end_bless(gm_client, pc["id"])
    return pcs


@pytest_asyncio.fixture
async def four_targets(gm_client, three_targets, roster):
    fourth = roster["Mira Greenleaf"]
    await _end_bless(gm_client, fourth["id"])
    return three_targets + [fourth]


@pytest_asyncio.fixture
async def five_targets(gm_client, four_targets, roster):
    fifth = roster["Thalindra Moonwhisper"]
    await _end_bless(gm_client, fifth["id"])
    return four_targets + [fifth]


async def test_bless_l1_three_targets_succeeds(
    gm_client, caelan, three_targets,
):
    """L1 Bless with 3 targets → 200 (RAW base cap)."""
    toks = await _seed_battle(gm_client, caelan, three_targets)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": caelan["id"],
            "spell_index": CAELAN_BLESS_INDEX,
            "slot_level": 1,
            "class_slug": "paladin",
            "target_combatant_ids": toks,
            "target_name": "Bless (L1, 3 targets)",
            "override": True,
            "override_range": True,
        },
    )
    assert resp.status_code == 200, resp.text
    # Cleanup — drop Caelan's concentration so subsequent tests cast fresh.
    await _end_caelan_concentration(gm_client, caelan["id"])
    for pc in three_targets:
        await _end_bless(gm_client, pc["id"])


async def test_bless_l1_four_targets_returns_400(
    gm_client, caelan, four_targets,
):
    """L1 Bless with 4 targets → 400 too_many_targets, limit=3."""
    toks = await _seed_battle(gm_client, caelan, four_targets)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": caelan["id"],
            "spell_index": CAELAN_BLESS_INDEX,
            "slot_level": 1,
            "class_slug": "paladin",
            "target_combatant_ids": toks,
            "target_name": "Bless (L1, 4 targets)",
            "override": True,
            "override_range": True,
        },
    )
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body.get("error") == "too_many_targets"
    assert body.get("limit") == 3
    assert body.get("received") == 4


async def test_bless_l2_four_targets_succeeds(
    gm_client, caelan, four_targets,
):
    """L2 Bless with 4 targets → 200 (extended cap = 3 + (2-1)*1 = 4)."""
    toks = await _seed_battle(gm_client, caelan, four_targets)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": caelan["id"],
            "spell_index": CAELAN_BLESS_INDEX,
            "slot_level": 2,
            "class_slug": "paladin",
            "target_combatant_ids": toks,
            "target_name": "Bless (L2, 4 targets)",
            "override": True,
            "override_range": True,
        },
    )
    assert resp.status_code == 200, resp.text
    # Cleanup
    await _end_caelan_concentration(gm_client, caelan["id"])
    for pc in four_targets:
        await _end_bless(gm_client, pc["id"])


async def test_bless_l2_five_targets_returns_400(
    gm_client, caelan, five_targets,
):
    """L2 Bless with 5 targets → 400 too_many_targets, limit=4 (the
    extended cap, not the base 3)."""
    toks = await _seed_battle(gm_client, caelan, five_targets)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": caelan["id"],
            "spell_index": CAELAN_BLESS_INDEX,
            "slot_level": 2,
            "class_slug": "paladin",
            "target_combatant_ids": toks,
            "target_name": "Bless (L2, 5 targets)",
            "override": True,
            "override_range": True,
        },
    )
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body.get("error") == "too_many_targets"
    # Confirms the new upcast field is being honored — limit is 4, not 3.
    assert body.get("limit") == 4
    assert body.get("received") == 5
