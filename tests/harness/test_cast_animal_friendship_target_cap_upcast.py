"""v2.404.8 — Animal Friendship condition-install + multi-target cap.

RAW PHB p.213: "This spell lets you convince a beast that you mean it
no harm. Choose a beast that you can see within range. It must see and
hear you. If the beast's Intelligence is 4 or higher, the spell fails.
Otherwise, the beast must succeed on a wisdom saving throw or be
charmed by you for the spell's duration." Higher Levels: "When you
cast this spell using a spell slot of 2nd level or higher, you can
affect one additional creature for each slot level above 1st."

Second **condition-install ship** of the v2.404.x arc (after Command
v2.404.7). Drop-in on the v2.404.7 recipe:
  - New `_SPELL_CONDITION_MAP["animal-friendship"]` entry installs a
    `befriended-beast` buff on a failed WIS save (NPC-only per v2.32.0;
    PC save-or-suck is filed). Duration 24 hours = 14400 rounds. No
    concentration. Effects list names the beast-only target gate +
    INT 4+ immunity.
  - New `_SPELL_TARGET_CAPS["animal-friendship"]` entry: `max_targets:
    1, base_level: 1, extra_targets_per_slot_above_base: 1`. Enforced
    by the v2.381.0 cap reader at `/cast_spell` before slot
    consumption.

Mira Greenleaf (Druid Lv 6) is the cast surface; her L1 + L2 slots
cover both base cap and +1 upcast extension. Animal Friendship is
appended at spell index 12 (after Longstrider at 11).

Tests:
  - L1 Animal Friendship with 1 target → 200 (base cap).
  - L1 Animal Friendship with 2 targets → 400 too_many_targets, limit=1.
  - L2 Animal Friendship with 2 targets → 200 (extended cap = 2).
  - L2 Animal Friendship with 3 targets → 400 too_many_targets, limit=2.
"""
from __future__ import annotations

import pytest_asyncio

from .conftest import CAMPAIGN_ID


# Mira Greenleaf's spell list (app/demo_seed.py:~3179-3201):
# Animal Friendship is appended at the END (after Longstrider at 11) → index 12.
MIRA_ANIMAL_FRIENDSHIP_INDEX = 12


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


async def _seed_battle(gm_client, mira, targets):
    """Seed a battle with Mira + N PC targets. The cap fires at
    /cast_spell entry, BEFORE save rolls — PCs are fine for the
    cap-enforcement contract."""
    combatants = [_mkc(
        f"tok_af_mira_{mira['id']}", mira["id"],
        name=mira["name"],
    )]
    target_toks = []
    for i, t in enumerate(targets):
        tok = f"tok_af_{t['id']}_{i}"
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
    return [pc]


@pytest_asyncio.fixture
async def two_targets(gm_client, one_target, roster):
    pc = roster["Krieger Stonefist"]
    return one_target + [pc]


@pytest_asyncio.fixture
async def three_targets(gm_client, two_targets, roster):
    pc = roster["Kael Brightleaf"]
    return two_targets + [pc]


async def test_animal_friendship_l1_one_target_succeeds(
    gm_client, mira, one_target,
):
    """L1 Animal Friendship with 1 target → 200 (RAW base cap)."""
    toks = await _seed_battle(gm_client, mira, one_target)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": mira["id"],
            "spell_index": MIRA_ANIMAL_FRIENDSHIP_INDEX,
            "slot_level": 1,
            "class_slug": "druid",
            "target_combatant_ids": toks,
            "target_name": "Animal Friendship (L1, 1 target)",
            "override": True,
            "override_range": True,
        },
    )
    assert resp.status_code == 200, resp.text


async def test_animal_friendship_l1_two_targets_returns_400(
    gm_client, mira, two_targets,
):
    """L1 Animal Friendship with 2 targets → 400 too_many_targets, limit=1."""
    toks = await _seed_battle(gm_client, mira, two_targets)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": mira["id"],
            "spell_index": MIRA_ANIMAL_FRIENDSHIP_INDEX,
            "slot_level": 1,
            "class_slug": "druid",
            "target_combatant_ids": toks,
            "target_name": "Animal Friendship (L1, 2 targets)",
            "override": True,
            "override_range": True,
        },
    )
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body.get("error") == "too_many_targets"
    assert body.get("limit") == 1
    assert body.get("received") == 2


async def test_animal_friendship_l2_two_targets_succeeds(
    gm_client, mira, two_targets,
):
    """L2 Animal Friendship with 2 targets → 200 (extended cap = 1 + (2-1)*1 = 2)."""
    toks = await _seed_battle(gm_client, mira, two_targets)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": mira["id"],
            "spell_index": MIRA_ANIMAL_FRIENDSHIP_INDEX,
            "slot_level": 2,
            "class_slug": "druid",
            "target_combatant_ids": toks,
            "target_name": "Animal Friendship (L2, 2 targets)",
            "override": True,
            "override_range": True,
        },
    )
    assert resp.status_code == 200, resp.text


async def test_animal_friendship_l2_three_targets_returns_400(
    gm_client, mira, three_targets,
):
    """L2 Animal Friendship with 3 targets → 400 too_many_targets,
    limit=2 (the extended cap, not the base 1)."""
    toks = await _seed_battle(gm_client, mira, three_targets)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": mira["id"],
            "spell_index": MIRA_ANIMAL_FRIENDSHIP_INDEX,
            "slot_level": 2,
            "class_slug": "druid",
            "target_combatant_ids": toks,
            "target_name": "Animal Friendship (L2, 3 targets)",
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
