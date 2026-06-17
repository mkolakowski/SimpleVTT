"""v2.404.9 — Blindness/Deafness condition-install + multi-target cap.

RAW PHB p.219: "You can blind or deafen a foe. Choose one creature
that you can see within range to make a Constitution saving throw. If
it fails, the target is either blinded or deafened (your choice) for
the duration." Higher Levels: "When you cast this spell using a spell
slot of 3rd level or higher, you can target one additional creature
for each slot level above 2nd." Duration: 1 minute. NOT concentration.
End-of-turn CON save to shake off.

**Arc-closer ship** of the v2.404.x spell utility-upcast arc:
  - New `_SPELL_CONDITION_MAP["blindnessdeafness"]` entry installs a
    `blinded` buff on a failed CON save (NPC-only v1; the deafened
    variant + caster-picker UI are filed for follow-up). Duration 10
    rounds. NOT concentration. Effects list names the blinded
    mechanical clauses + the end-of-turn CON save.
  - New `_SPELL_TARGET_CAPS["blindnessdeafness"]` entry: `max_targets:
    1, base_level: 2, extra_targets_per_slot_above_base: 1`. First
    L2-base condition-install spell to use the substrate.

Lyra Sunstrider (Bard Lv 6) is the cast surface; her L2 + L3 slots
cover both base cap and +1 upcast extension. Blindness/Deafness is
appended at spell index 20 (after Fear at 19). SRD slug is
`blindnessdeafness` (no separator) — the JSON catalog smashes the words
together.

Tests:
  - L2 Blindness/Deafness with 1 target → 200 (base cap).
  - L2 Blindness/Deafness with 2 targets → 400 too_many_targets, limit=1.
  - L3 Blindness/Deafness with 2 targets → 200 (extended cap = 2).
  - L3 Blindness/Deafness with 3 targets → 400 too_many_targets, limit=2.
"""
from __future__ import annotations

import pytest_asyncio

from .conftest import CAMPAIGN_ID


# Lyra Sunstrider's spell list (app/demo_seed.py:~2668-2720):
# Blindness/Deafness is appended at the END (after Fear at 19) → index 20.
LYRA_BLINDNESS_DEAFNESS_INDEX = 20


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


async def _seed_battle(gm_client, lyra, targets):
    """Seed a battle with Lyra + N PC targets. The cap fires at
    /cast_spell entry, BEFORE save rolls — PCs are fine for the
    cap-enforcement contract."""
    combatants = [_mkc(
        f"tok_bd_lyra_{lyra['id']}", lyra["id"],
        name=lyra["name"],
    )]
    target_toks = []
    for i, t in enumerate(targets):
        tok = f"tok_bd_{t['id']}_{i}"
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
    return lyra


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


async def test_blindness_deafness_l2_one_target_succeeds(
    gm_client, lyra, one_target,
):
    """L2 Blindness/Deafness with 1 target → 200 (RAW base cap)."""
    toks = await _seed_battle(gm_client, lyra, one_target)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": lyra["id"],
            "spell_index": LYRA_BLINDNESS_DEAFNESS_INDEX,
            "slot_level": 2,
            "class_slug": "bard",
            "target_combatant_ids": toks,
            "target_name": "Blindness/Deafness (L2, 1 target)",
            "override": True,
            "override_range": True,
        },
    )
    assert resp.status_code == 200, resp.text


async def test_blindness_deafness_l2_two_targets_returns_400(
    gm_client, lyra, two_targets,
):
    """L2 Blindness/Deafness with 2 targets → 400 too_many_targets, limit=1."""
    toks = await _seed_battle(gm_client, lyra, two_targets)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": lyra["id"],
            "spell_index": LYRA_BLINDNESS_DEAFNESS_INDEX,
            "slot_level": 2,
            "class_slug": "bard",
            "target_combatant_ids": toks,
            "target_name": "Blindness/Deafness (L2, 2 targets)",
            "override": True,
            "override_range": True,
        },
    )
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body.get("error") == "too_many_targets"
    assert body.get("limit") == 1
    assert body.get("received") == 2


async def test_blindness_deafness_l3_two_targets_succeeds(
    gm_client, lyra, two_targets,
):
    """L3 Blindness/Deafness with 2 targets → 200 (extended cap = 1 + (3-2)*1 = 2)."""
    toks = await _seed_battle(gm_client, lyra, two_targets)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": lyra["id"],
            "spell_index": LYRA_BLINDNESS_DEAFNESS_INDEX,
            "slot_level": 3,
            "class_slug": "bard",
            "target_combatant_ids": toks,
            "target_name": "Blindness/Deafness (L3, 2 targets)",
            "override": True,
            "override_range": True,
        },
    )
    assert resp.status_code == 200, resp.text


async def test_blindness_deafness_l3_three_targets_returns_400(
    gm_client, lyra, three_targets,
):
    """L3 Blindness/Deafness with 3 targets → 400 too_many_targets,
    limit=2 (the extended cap, not the base 1)."""
    toks = await _seed_battle(gm_client, lyra, three_targets)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": lyra["id"],
            "spell_index": LYRA_BLINDNESS_DEAFNESS_INDEX,
            "slot_level": 3,
            "class_slug": "bard",
            "target_combatant_ids": toks,
            "target_name": "Blindness/Deafness (L3, 3 targets)",
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
