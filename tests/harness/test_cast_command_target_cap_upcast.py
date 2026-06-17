"""v2.404.7 — Command condition-install + multi-target cap.

RAW PHB p.223: "You speak a one-word command to a creature you can see
within range. The target must succeed on a wisdom saving throw or
follow the command on its next turn." Higher Levels: "When you cast
this spell using a spell slot of 2nd level or higher, you can affect
one additional creature for each slot level above 1st."

First **condition-install ship** of the v2.404.x arc:
  - New `_SPELL_CONDITION_MAP["command"]` entry installs a `commanded`
    buff on a failed WIS save (NPC-only per v2.32.0; PC save-or-suck
    is filed). Duration 1 round, no concentration. Effects list names
    the 6 RAW commands (Approach / Drop / Flee / Grovel / Halt / other)
    for GM-narrated enforcement.
  - New `_SPELL_TARGET_CAPS["command"]` entry: `max_targets: 1,
    base_level: 1, extra_targets_per_slot_above_base: 1`. Enforced
    by the v2.381.0 cap reader at `/cast_spell` before slot
    consumption.

Brother Tavik Stonebrow (Cleric Lv 8) is the cast surface; his L1 + L2
slots cover both base cap and +1 upcast extension. Command is appended
at spell index 14 (after Enhance Ability at 13).

Tests:
  - L1 Command with 1 target → 200 (base cap).
  - L1 Command with 2 targets → 400 too_many_targets, limit=1.
  - L2 Command with 2 targets → 200 (extended cap = 2).
  - L2 Command with 3 targets → 400 too_many_targets, limit=2.

Note: the per-target Commanded install on a failed save is filed for a
follow-up test (needs an NPC target + a forced-fail mechanism for the
WIS save). The cap-enforcement contract is what this file asserts.
"""
from __future__ import annotations

import pytest_asyncio

from .conftest import CAMPAIGN_ID


# Brother Tavik Stonebrow's spell list (app/demo_seed.py:~1449-1467):
# Command is appended at the END (after Enhance Ability at 13) → index 14.
TAVIK_COMMAND_INDEX = 14


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


async def _seed_battle(gm_client, tavik, targets):
    """Seed a battle with Tavik + N PC targets. Command's cap fires at
    /cast_spell entry, BEFORE save rolls — so PCs are fine for the
    cap-enforcement contract (whether the WIS save passes/fails is
    irrelevant; the install path is NPC-only in v1)."""
    combatants = [_mkc(
        f"tok_cmd_tavik_{tavik['id']}", tavik["id"],
        name=tavik["name"],
    )]
    target_toks = []
    for i, t in enumerate(targets):
        tok = f"tok_cmd_{t['id']}_{i}"
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


async def test_command_l1_one_target_succeeds(
    gm_client, tavik, one_target,
):
    """L1 Command with 1 target → 200 (RAW base cap)."""
    toks = await _seed_battle(gm_client, tavik, one_target)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": tavik["id"],
            "spell_index": TAVIK_COMMAND_INDEX,
            "slot_level": 1,
            "class_slug": "cleric",
            "target_combatant_ids": toks,
            "target_name": "Command (L1, 1 target)",
            "override": True,
            "override_range": True,
        },
    )
    assert resp.status_code == 200, resp.text


async def test_command_l1_two_targets_returns_400(
    gm_client, tavik, two_targets,
):
    """L1 Command with 2 targets → 400 too_many_targets, limit=1.

    Confirms the v2.381.0 cap reader at /cast_spell honors the new
    `_SPELL_TARGET_CAPS["command"]` entry."""
    toks = await _seed_battle(gm_client, tavik, two_targets)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": tavik["id"],
            "spell_index": TAVIK_COMMAND_INDEX,
            "slot_level": 1,
            "class_slug": "cleric",
            "target_combatant_ids": toks,
            "target_name": "Command (L1, 2 targets)",
            "override": True,
            "override_range": True,
        },
    )
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body.get("error") == "too_many_targets"
    assert body.get("limit") == 1
    assert body.get("received") == 2


async def test_command_l2_two_targets_succeeds(
    gm_client, tavik, two_targets,
):
    """L2 Command with 2 targets → 200 (extended cap = 1 + (2-1)*1 = 2)."""
    toks = await _seed_battle(gm_client, tavik, two_targets)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": tavik["id"],
            "spell_index": TAVIK_COMMAND_INDEX,
            "slot_level": 2,
            "class_slug": "cleric",
            "target_combatant_ids": toks,
            "target_name": "Command (L2, 2 targets)",
            "override": True,
            "override_range": True,
        },
    )
    assert resp.status_code == 200, resp.text


async def test_command_l2_three_targets_returns_400(
    gm_client, tavik, three_targets,
):
    """L2 Command with 3 targets → 400 too_many_targets, limit=2 (the
    extended cap, not the base 1)."""
    toks = await _seed_battle(gm_client, tavik, three_targets)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": tavik["id"],
            "spell_index": TAVIK_COMMAND_INDEX,
            "slot_level": 2,
            "class_slug": "cleric",
            "target_combatant_ids": toks,
            "target_name": "Command (L2, 3 targets)",
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
