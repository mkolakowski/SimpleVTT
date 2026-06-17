"""v2.404.1 — Invisibility multi-target cap + per-slot upcast scaling.

RAW PHB p.254: "A creature you touch becomes invisible until the spell
ends." Higher Levels: "When you cast this spell using a spell slot of 3rd
level or higher, you can target one additional creature for each slot
level above 2nd."

The v2.404.1 `_SPELL_BUFF_MAP["invisibility"]` entry carries:
  - `max_targets: 1`             (RAW base cap at L2)
  - `base_level: 2`              (the slot level the cap applies at)
  - `extra_targets_per_slot_above_base: 1`  (cap grows +1/slot above base)

The /cast_spell `max_targets` gate (v2.372.1 — originally added for Aid,
extended for upcasting in v2.380.0 for Bless) reads these fields and
extends the effective cap by `(slot_level - base_level) * extra_per_slot`.
Aid keeps its hard 3-cap and Bless keeps its L1+1/slot shape — Invisibility
is the first L2-base spell to use the substrate.

Tests:
  - L2 Invisibility with 1 target → 200 (base cap).
  - L2 Invisibility with 2 targets → 400 too_many_targets, limit=1.
  - L3 Invisibility with 2 targets → 200 (extended cap = 2).
  - L3 Invisibility with 3 targets → 400 too_many_targets, limit=2.
"""
from __future__ import annotations

import pytest_asyncio

from .conftest import CAMPAIGN_ID


# Lyra Sunstrider's spell list (app/demo_seed.py:~2668-2719):
#   0 Vicious Mockery, 1 Mage Hand, 2 Minor Illusion,
#   3 Prestidigitation, 4 Healing Word, 5 Cure Wounds,
#   6 Faerie Fire, 7 Heroism, 8 Thunderwave, 9 Suggestion,
#   10 Invisibility ← target index for this suite
LYRA_INVISIBILITY_INDEX = 10


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


async def _end_invisibility(gm_client, char_id):
    """Drop any pre-existing Invisibility buff on the target so the cast
    can install fresh (concentration would otherwise mask leftover state
    from prior tests)."""
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": char_id, "key": "invisibility"},
    )


async def _end_lyra_concentration(gm_client, lyra_id):
    """Drop Lyra's Invisibility concentration before each test so the
    prior cast doesn't displace via the concentration swap rule."""
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": lyra_id, "key": "invisibility"},
    )


async def _seed_battle(gm_client, lyra, targets):
    """Seed a battle with Lyra + N PC targets. Returns target combatant
    id list in placement order."""
    combatants = [_mkc(
        f"tok_inv_lyra_{lyra['id']}", lyra["id"],
        name=lyra["name"],
    )]
    target_toks = []
    for i, t in enumerate(targets):
        tok = f"tok_inv_{t['id']}_{i}"
        combatants.append(_mkc(tok, t["id"], name=t["name"]))
        target_toks.append(tok)
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )
    return target_toks


@pytest_asyncio.fixture
async def lyra(gm_client, roster):
    lyra = roster["Lyra Sunstrider"]
    await _long_rest(gm_client, lyra["id"])
    await _end_lyra_concentration(gm_client, lyra["id"])
    return lyra


@pytest_asyncio.fixture
async def one_target(gm_client, roster):
    pc = roster["Pip Quickfingers"]
    await _end_invisibility(gm_client, pc["id"])
    return [pc]


@pytest_asyncio.fixture
async def two_targets(gm_client, one_target, roster):
    pc = roster["Krieger Stonefist"]
    await _end_invisibility(gm_client, pc["id"])
    return one_target + [pc]


@pytest_asyncio.fixture
async def three_targets(gm_client, two_targets, roster):
    pc = roster["Kael Brightleaf"]
    await _end_invisibility(gm_client, pc["id"])
    return two_targets + [pc]


async def test_invisibility_l2_one_target_succeeds(
    gm_client, lyra, one_target,
):
    """L2 Invisibility with 1 target → 200 (RAW base cap)."""
    toks = await _seed_battle(gm_client, lyra, one_target)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": lyra["id"],
            "spell_index": LYRA_INVISIBILITY_INDEX,
            "slot_level": 2,
            "class_slug": "bard",
            "target_combatant_ids": toks,
            "target_name": "Invisibility (L2, 1 target)",
            "override": True,
            "override_range": True,
        },
    )
    assert resp.status_code == 200, resp.text
    # Cleanup so subsequent tests cast fresh.
    await _end_lyra_concentration(gm_client, lyra["id"])
    for pc in one_target:
        await _end_invisibility(gm_client, pc["id"])


async def test_invisibility_l2_two_targets_returns_400(
    gm_client, lyra, two_targets,
):
    """L2 Invisibility with 2 targets → 400 too_many_targets, limit=1."""
    toks = await _seed_battle(gm_client, lyra, two_targets)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": lyra["id"],
            "spell_index": LYRA_INVISIBILITY_INDEX,
            "slot_level": 2,
            "class_slug": "bard",
            "target_combatant_ids": toks,
            "target_name": "Invisibility (L2, 2 targets)",
            "override": True,
            "override_range": True,
        },
    )
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body.get("error") == "too_many_targets"
    assert body.get("limit") == 1
    assert body.get("received") == 2


async def test_invisibility_l3_two_targets_succeeds(
    gm_client, lyra, two_targets,
):
    """L3 Invisibility with 2 targets → 200 (extended cap = 1 + (3-2)*1 = 2)."""
    toks = await _seed_battle(gm_client, lyra, two_targets)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": lyra["id"],
            "spell_index": LYRA_INVISIBILITY_INDEX,
            "slot_level": 3,
            "class_slug": "bard",
            "target_combatant_ids": toks,
            "target_name": "Invisibility (L3, 2 targets)",
            "override": True,
            "override_range": True,
        },
    )
    assert resp.status_code == 200, resp.text
    # Cleanup.
    await _end_lyra_concentration(gm_client, lyra["id"])
    for pc in two_targets:
        await _end_invisibility(gm_client, pc["id"])


async def test_invisibility_l3_three_targets_returns_400(
    gm_client, lyra, three_targets,
):
    """L3 Invisibility with 3 targets → 400 too_many_targets, limit=2 (the
    extended cap, not the base 1)."""
    toks = await _seed_battle(gm_client, lyra, three_targets)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": lyra["id"],
            "spell_index": LYRA_INVISIBILITY_INDEX,
            "slot_level": 3,
            "class_slug": "bard",
            "target_combatant_ids": toks,
            "target_name": "Invisibility (L3, 3 targets)",
            "override": True,
            "override_range": True,
        },
    )
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body.get("error") == "too_many_targets"
    # Confirms the upcast field is being honored — limit is 2, not 1.
    assert body.get("limit") == 2
    assert body.get("received") == 3
