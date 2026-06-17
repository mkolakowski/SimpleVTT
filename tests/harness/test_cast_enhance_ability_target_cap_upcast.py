"""v2.404.3 — Enhance Ability multi-target cap + per-slot upcast scaling.

RAW PHB p.237: "You touch a creature and bestow upon it a magical
enhancement. Choose one of the following effects [Bear / Bull / Cat /
Eagle / Fox / Owl variant] ... the target gains that effect until the
spell ends." Higher Levels: "When you cast this spell using a spell slot
of 3rd level or higher, you can target one additional creature for each
slot level above 2nd."

The v2.404.3 `_SPELL_BUFF_MAP["enhance-ability"]` entry carries:
  - `max_targets: 1`             (RAW base cap at L2)
  - `base_level: 2`              (the slot level the cap applies at)
  - `extra_targets_per_slot_above_base: 1`  (cap grows +1/slot above base)

Same shape as Invisibility (v2.404.1) — L2 base with +1/slot above.
Tavik (Cleric Lv 8) is the cast surface; his L2 + L3 slots cover both
base cap and +1 upcast extension. The six variant choices + variant
rider effects (temp HP, carrying capacity, fall protection) stay
GM-narrated.

Tests:
  - L2 Enhance Ability with 1 target → 200 (base cap).
  - L2 Enhance Ability with 2 targets → 400 too_many_targets, limit=1.
  - L3 Enhance Ability with 2 targets → 200 (extended cap = 2).
  - L3 Enhance Ability with 3 targets → 400 too_many_targets, limit=2.
"""
from __future__ import annotations

import pytest_asyncio

from .conftest import CAMPAIGN_ID


# Brother Tavik Stonebrow's spell list (app/demo_seed.py:~1449-1467):
# Enhance Ability is appended at the END (after Mass Healing Word at 12)
# → index 13. The full ordering:
#   0 Sacred Flame, 1 Guidance, 2 Light,
#   3 Bless, 4 Cure Wounds, 5 Healing Word,
#   6 Lesser Restoration, 7 Spiritual Weapon, 8 Hold Person,
#   9 Beacon of Hope, 10 Revivify, 11 Spirit Guardians,
#   12 Mass Healing Word, 13 Enhance Ability ← new.
TAVIK_ENHANCE_ABILITY_INDEX = 13


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


async def _end_enhance_ability(gm_client, char_id):
    """Drop any pre-existing Enhance Ability buff on the target so the
    cast can install fresh."""
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": char_id, "key": "enhance-ability"},
    )


async def _end_tavik_concentration(gm_client, tavik_id):
    """Drop Tavik's Enhance Ability concentration before each test."""
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": tavik_id, "key": "enhance-ability"},
    )


async def _seed_battle(gm_client, tavik, targets):
    """Seed a battle with Tavik + N PC targets. Returns target combatant
    id list in placement order."""
    combatants = [_mkc(
        f"tok_eha_tavik_{tavik['id']}", tavik["id"],
        name=tavik["name"],
    )]
    target_toks = []
    for i, t in enumerate(targets):
        tok = f"tok_eha_{t['id']}_{i}"
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
    await _end_tavik_concentration(gm_client, tavik["id"])
    return tavik


@pytest_asyncio.fixture
async def one_target(gm_client, roster):
    pc = roster["Pip Quickfingers"]
    await _end_enhance_ability(gm_client, pc["id"])
    return [pc]


@pytest_asyncio.fixture
async def two_targets(gm_client, one_target, roster):
    pc = roster["Krieger Stonefist"]
    await _end_enhance_ability(gm_client, pc["id"])
    return one_target + [pc]


@pytest_asyncio.fixture
async def three_targets(gm_client, two_targets, roster):
    pc = roster["Kael Brightleaf"]
    await _end_enhance_ability(gm_client, pc["id"])
    return two_targets + [pc]


async def test_enhance_ability_l2_one_target_succeeds(
    gm_client, tavik, one_target,
):
    """L2 Enhance Ability with 1 target → 200 (RAW base cap)."""
    toks = await _seed_battle(gm_client, tavik, one_target)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": tavik["id"],
            "spell_index": TAVIK_ENHANCE_ABILITY_INDEX,
            "slot_level": 2,
            "class_slug": "cleric",
            "target_combatant_ids": toks,
            "target_name": "Enhance Ability (L2, 1 target)",
            "override": True,
            "override_range": True,
        },
    )
    assert resp.status_code == 200, resp.text
    # Cleanup.
    await _end_tavik_concentration(gm_client, tavik["id"])
    for pc in one_target:
        await _end_enhance_ability(gm_client, pc["id"])


async def test_enhance_ability_l2_two_targets_returns_400(
    gm_client, tavik, two_targets,
):
    """L2 Enhance Ability with 2 targets → 400 too_many_targets, limit=1."""
    toks = await _seed_battle(gm_client, tavik, two_targets)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": tavik["id"],
            "spell_index": TAVIK_ENHANCE_ABILITY_INDEX,
            "slot_level": 2,
            "class_slug": "cleric",
            "target_combatant_ids": toks,
            "target_name": "Enhance Ability (L2, 2 targets)",
            "override": True,
            "override_range": True,
        },
    )
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body.get("error") == "too_many_targets"
    assert body.get("limit") == 1
    assert body.get("received") == 2


async def test_enhance_ability_l3_two_targets_succeeds(
    gm_client, tavik, two_targets,
):
    """L3 Enhance Ability with 2 targets → 200 (extended cap = 1 + (3-2)*1 = 2)."""
    toks = await _seed_battle(gm_client, tavik, two_targets)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": tavik["id"],
            "spell_index": TAVIK_ENHANCE_ABILITY_INDEX,
            "slot_level": 3,
            "class_slug": "cleric",
            "target_combatant_ids": toks,
            "target_name": "Enhance Ability (L3, 2 targets)",
            "override": True,
            "override_range": True,
        },
    )
    assert resp.status_code == 200, resp.text
    # Cleanup.
    await _end_tavik_concentration(gm_client, tavik["id"])
    for pc in two_targets:
        await _end_enhance_ability(gm_client, pc["id"])


async def test_enhance_ability_l3_three_targets_returns_400(
    gm_client, tavik, three_targets,
):
    """L3 Enhance Ability with 3 targets → 400 too_many_targets, limit=2
    (the extended cap, not the base 1)."""
    toks = await _seed_battle(gm_client, tavik, three_targets)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": tavik["id"],
            "spell_index": TAVIK_ENHANCE_ABILITY_INDEX,
            "slot_level": 3,
            "class_slug": "cleric",
            "target_combatant_ids": toks,
            "target_name": "Enhance Ability (L3, 3 targets)",
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
