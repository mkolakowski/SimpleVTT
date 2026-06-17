"""v2.404.5 — Charm Person multi-target cap + per-slot upcast scaling.

RAW PHB p.221: "One humanoid you choose within range you can see ...
must make a wisdom saving throw, and does so with advantage if you or
your companions are fighting it. If it fails the saving throw, it is
charmed by you until the spell ends or until you or your companions
do anything harmful to it." Higher Levels: "When you cast this spell
using a spell slot of 2nd level or higher, you can target one
additional creature for each slot level above 1st. The creatures must
be within 30 feet of each other when you target them."

The v2.404.5 `_SPELL_TARGET_CAPS["charm-person"]` entry carries:
  - `max_targets: 1`             (RAW base cap at L1)
  - `base_level: 1`              (the slot level the cap applies at)
  - `extra_targets_per_slot_above_base: 1`  (cap grows +1/slot above base)

First **condition-shape** spell to use the v2.381.0 generalized
`_SPELL_TARGET_CAPS` substrate (Mass Healing Word + Mass Cure Wounds
are heal-shape). The save-or-suck Charmed install on a failed WIS save
flows through `_SPELL_CONDITION_MAP["charm-person"]` (1-hour, no
concentration) unchanged.

Thalindra Moonwhisper (Wizard Lv 7) is the cast surface; her L1 + L2
slots cover both base cap and +1 upcast extension. Charm Person is
appended at spell index 21 — END-append preserves all existing
spell_index assertions in the harness.

Tests:
  - L1 Charm Person with 1 target → 200 (base cap).
  - L1 Charm Person with 2 targets → 400 too_many_targets, limit=1.
  - L2 Charm Person with 2 targets → 200 (extended cap = 2).
  - L2 Charm Person with 3 targets → 400 too_many_targets, limit=2.
"""
from __future__ import annotations

import pytest_asyncio

from .conftest import CAMPAIGN_ID


# Thalindra Moonwhisper's spell list (app/demo_seed.py:~764-897):
# Charm Person is appended at the END (after Fly at 20) → index 21.
THALINDRA_CHARM_PERSON_INDEX = 21


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


async def _seed_battle(gm_client, thalindra, targets):
    """Seed a battle with Thalindra + N NPC targets. Charm Person caps
    fire at /cast_spell entry, BEFORE save rolls — so the targets can
    be PCs or NPCs; the cap doesn't depend on save resolution.
    """
    combatants = [_mkc(
        f"tok_chp_thal_{thalindra['id']}", thalindra["id"],
        name=thalindra["name"],
    )]
    target_toks = []
    for i, t in enumerate(targets):
        tok = f"tok_chp_{t['id']}_{i}"
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
    return thalindra


@pytest_asyncio.fixture
async def one_target(gm_client, roster):
    pc = roster["Pip Quickfingers"]
    return [pc]


@pytest_asyncio.fixture
async def two_targets(gm_client, one_target, roster):
    pc = roster["Krieger Stonefist"]
    return one_target + [pc]


@pytest_asyncio.fixture
async def three_targets(gm_client, two_targets, roster):
    pc = roster["Kael Brightleaf"]
    return two_targets + [pc]


async def test_charm_person_l1_one_target_succeeds(
    gm_client, thalindra, one_target,
):
    """L1 Charm Person with 1 target → 200 (RAW base cap).

    The cap reader fires BEFORE save rolls, so a 200 here means the
    cap accepted 1 target; whether the WIS save passed/failed is
    irrelevant to this test."""
    toks = await _seed_battle(gm_client, thalindra, one_target)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thalindra["id"],
            "spell_index": THALINDRA_CHARM_PERSON_INDEX,
            "slot_level": 1,
            "class_slug": "wizard",
            "target_combatant_ids": toks,
            "target_name": "Charm Person (L1, 1 target)",
            "override": True,
            "override_range": True,
        },
    )
    assert resp.status_code == 200, resp.text


async def test_charm_person_l1_two_targets_returns_400(
    gm_client, thalindra, two_targets,
):
    """L1 Charm Person with 2 targets → 400 too_many_targets, limit=1.

    Confirms the v2.381.0 cap reader at /cast_spell honors the new
    `_SPELL_TARGET_CAPS["charm-person"]` entry."""
    toks = await _seed_battle(gm_client, thalindra, two_targets)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thalindra["id"],
            "spell_index": THALINDRA_CHARM_PERSON_INDEX,
            "slot_level": 1,
            "class_slug": "wizard",
            "target_combatant_ids": toks,
            "target_name": "Charm Person (L1, 2 targets)",
            "override": True,
            "override_range": True,
        },
    )
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body.get("error") == "too_many_targets"
    assert body.get("limit") == 1
    assert body.get("received") == 2


async def test_charm_person_l2_two_targets_succeeds(
    gm_client, thalindra, two_targets,
):
    """L2 Charm Person with 2 targets → 200 (extended cap = 1 + (2-1)*1 = 2)."""
    toks = await _seed_battle(gm_client, thalindra, two_targets)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thalindra["id"],
            "spell_index": THALINDRA_CHARM_PERSON_INDEX,
            "slot_level": 2,
            "class_slug": "wizard",
            "target_combatant_ids": toks,
            "target_name": "Charm Person (L2, 2 targets)",
            "override": True,
            "override_range": True,
        },
    )
    assert resp.status_code == 200, resp.text


async def test_charm_person_l2_three_targets_returns_400(
    gm_client, thalindra, three_targets,
):
    """L2 Charm Person with 3 targets → 400 too_many_targets, limit=2
    (the extended cap, not the base 1)."""
    toks = await _seed_battle(gm_client, thalindra, three_targets)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thalindra["id"],
            "spell_index": THALINDRA_CHARM_PERSON_INDEX,
            "slot_level": 2,
            "class_slug": "wizard",
            "target_combatant_ids": toks,
            "target_name": "Charm Person (L2, 3 targets)",
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
