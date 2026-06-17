"""v2.404.2 — Fly multi-target cap + per-slot upcast scaling.

RAW PHB p.244: "Touch a willing creature. The target gains a flying speed
of 60 feet for the duration." Higher Levels: "When you cast this spell
using a spell slot of 4th level or higher, you can target one additional
creature for each slot level above 3rd."

The v2.404.2 `_SPELL_BUFF_MAP["fly"]` entry carries:
  - `max_targets: 1`             (RAW base cap at L3)
  - `base_level: 3`              (the slot level the cap applies at)
  - `extra_targets_per_slot_above_base: 1`  (cap grows +1/slot above base)

Fly is the first L3-base spell to use the v2.380.0 cap+upcast substrate
(Bless = L1 base, Aid = L2 base no-extra, Invisibility = L2 base, Fly =
L3 base). Thalindra (Wizard Lv 7) is the cast surface — her L3 + L4 slots
let the harness exercise both base cap and the +1 upcast extension without
PATCHing in a slot.

Tests:
  - L3 Fly with 1 target → 200 (base cap).
  - L3 Fly with 2 targets → 400 too_many_targets, limit=1.
  - L4 Fly with 2 targets → 200 (extended cap = 2).
  - L4 Fly with 3 targets → 400 too_many_targets, limit=2.
"""
from __future__ import annotations

import pytest_asyncio

from .conftest import CAMPAIGN_ID


# Thalindra Moonwhisper's spell list (app/demo_seed.py:~764-879):
# Fly is appended at the END (after Gust of Wind at 19) → index 20.
# The full ordering: 0 Fire Bolt, 1 Mage Hand, 2 Prestidigitation,
# 3 Magic Missile, 4 Shield, 5 Misty Step, 6 Scorching Ray, 7 Web,
# 8 Hold Monster, 9 Flesh to Stone, 10 Fireball, 11 Lightning Bolt,
# 12 Counterspell, 13 Slow, 14 Sleep, 15 Silvery Barbs, 16 Confusion,
# 17 Banishment, 18 Poison Spray, 19 Gust of Wind, 20 Fly.
THALINDRA_FLY_INDEX = 20


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


async def _end_fly(gm_client, char_id):
    """Drop any pre-existing Fly buff on the target so the cast can
    install fresh."""
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": char_id, "key": "fly"},
    )


async def _end_thalindra_concentration(gm_client, thalindra_id):
    """Drop Thalindra's Fly concentration before each test (concentration
    swap rule)."""
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": thalindra_id, "key": "fly"},
    )


async def _seed_battle(gm_client, thalindra, targets):
    """Seed a battle with Thalindra + N PC targets. Returns target
    combatant id list in placement order."""
    combatants = [_mkc(
        f"tok_fly_thal_{thalindra['id']}", thalindra["id"],
        name=thalindra["name"],
    )]
    target_toks = []
    for i, t in enumerate(targets):
        tok = f"tok_fly_{t['id']}_{i}"
        combatants.append(_mkc(tok, t["id"], name=t["name"]))
        target_toks.append(tok)
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )
    return target_toks


@pytest_asyncio.fixture
async def thalindra(gm_client, roster):
    thalindra = roster["Thalindra Moonwhisper"]
    await _long_rest(gm_client, thalindra["id"])
    await _end_thalindra_concentration(gm_client, thalindra["id"])
    return thalindra


@pytest_asyncio.fixture
async def one_target(gm_client, roster):
    pc = roster["Pip Quickfingers"]
    await _end_fly(gm_client, pc["id"])
    return [pc]


@pytest_asyncio.fixture
async def two_targets(gm_client, one_target, roster):
    pc = roster["Krieger Stonefist"]
    await _end_fly(gm_client, pc["id"])
    return one_target + [pc]


@pytest_asyncio.fixture
async def three_targets(gm_client, two_targets, roster):
    pc = roster["Kael Brightleaf"]
    await _end_fly(gm_client, pc["id"])
    return two_targets + [pc]


async def test_fly_l3_one_target_succeeds(
    gm_client, thalindra, one_target,
):
    """L3 Fly with 1 target → 200 (RAW base cap)."""
    toks = await _seed_battle(gm_client, thalindra, one_target)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thalindra["id"],
            "spell_index": THALINDRA_FLY_INDEX,
            "slot_level": 3,
            "class_slug": "wizard",
            "target_combatant_ids": toks,
            "target_name": "Fly (L3, 1 target)",
            "override": True,
            "override_range": True,
        },
    )
    assert resp.status_code == 200, resp.text
    # Cleanup.
    await _end_thalindra_concentration(gm_client, thalindra["id"])
    for pc in one_target:
        await _end_fly(gm_client, pc["id"])


async def test_fly_l3_two_targets_returns_400(
    gm_client, thalindra, two_targets,
):
    """L3 Fly with 2 targets → 400 too_many_targets, limit=1."""
    toks = await _seed_battle(gm_client, thalindra, two_targets)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thalindra["id"],
            "spell_index": THALINDRA_FLY_INDEX,
            "slot_level": 3,
            "class_slug": "wizard",
            "target_combatant_ids": toks,
            "target_name": "Fly (L3, 2 targets)",
            "override": True,
            "override_range": True,
        },
    )
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body.get("error") == "too_many_targets"
    assert body.get("limit") == 1
    assert body.get("received") == 2


async def test_fly_l4_two_targets_succeeds(
    gm_client, thalindra, two_targets,
):
    """L4 Fly with 2 targets → 200 (extended cap = 1 + (4-3)*1 = 2)."""
    toks = await _seed_battle(gm_client, thalindra, two_targets)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thalindra["id"],
            "spell_index": THALINDRA_FLY_INDEX,
            "slot_level": 4,
            "class_slug": "wizard",
            "target_combatant_ids": toks,
            "target_name": "Fly (L4, 2 targets)",
            "override": True,
            "override_range": True,
        },
    )
    assert resp.status_code == 200, resp.text
    # Cleanup.
    await _end_thalindra_concentration(gm_client, thalindra["id"])
    for pc in two_targets:
        await _end_fly(gm_client, pc["id"])


async def test_fly_l4_three_targets_returns_400(
    gm_client, thalindra, three_targets,
):
    """L4 Fly with 3 targets → 400 too_many_targets, limit=2 (the
    extended cap, not the base 1)."""
    toks = await _seed_battle(gm_client, thalindra, three_targets)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thalindra["id"],
            "spell_index": THALINDRA_FLY_INDEX,
            "slot_level": 4,
            "class_slug": "wizard",
            "target_combatant_ids": toks,
            "target_name": "Fly (L4, 3 targets)",
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
