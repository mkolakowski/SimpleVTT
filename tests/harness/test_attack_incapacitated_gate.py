"""v2.386.0 — /attack incapacitated gate.

RAW PHB p.290 Incapacitated: "An incapacitated creature can't take
actions or reactions." Closes clause #2a of the v2.384.0
condition-enforcement audit (Incapacitated general action gate). The
v2.386.0 gate fires BEFORE the over-budget check at /attack so a
blocked attempt doesn't burn the action slot. Uses the v2.385.0
shared `_caster_is_incapacitated()` helper, which reads the existing
`_INCAPACITATING_BUFF_KEYS` set (paralyzed / stunned / unconscious /
petrified / asleep / Hideous-Laughter).

Follow-up commits will wire the same helper into `/cast_spell` and
`/use_feature` (clause #2b/#2c).

Tests:
  - A paralyzed PC calling /attack → 409 `incapacitated` with the
    char_name + source + label echoed; no roll fires.
  - The same PC with `override: true` in the body → the gate is
    bypassed; the attack rolls normally (200).
  - A non-incapacitated PC → /attack proceeds unchanged (200).
"""
from __future__ import annotations

import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def caelan_rested(gm_client, roster):
    """Long-rest Caelan so action slot + class resources are fresh."""
    caelan = roster["Sir Caelan Lightbringer"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/rest",
        json={"type": "long"},
    )
    return caelan


def _make_combatant(name, char_id, hp=50, init=10, buffs=None):
    return {
        "id": f"tok_inc_{char_id}",
        "char_id": char_id,
        "name": name,
        "initiative": init,
        "hp_current": hp, "hp_max": hp,
        "buffs": buffs or [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


PARALYZED_BUFF = {
    "key": "paralyzed",
    "name": "Paralyzed (Hold Person)",
    "icon": "🥶",
    "duration_rounds": 10,
    "concentration": False,
}


async def test_paralyzed_caster_attack_returns_409(
    gm_client, caelan_rested, roster,
):
    """Caelan is paralyzed; calling /attack returns 409
    `incapacitated` and the action slot is NOT consumed."""
    caelan = caelan_rested
    krieger = roster["Krieger Stonefist"]
    await _seed_battle(gm_client, [
        _make_combatant(caelan["name"], caelan["id"],
                        buffs=[PARALYZED_BUFF]),
        _make_combatant(krieger["name"], krieger["id"]),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": caelan["id"],
            "attack_index": 0,
            "target_combatant_id": f"tok_inc_{krieger['id']}",
        },
    )
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body.get("error") == "incapacitated"
    assert body.get("char_name") == caelan["name"]
    assert body.get("source") == "attack"


async def test_paralyzed_caster_attack_with_override_succeeds(
    gm_client, caelan_rested, roster,
):
    """Same setup but with `override: True` → the gate is bypassed;
    the attack rolls normally (200). RAW would block this, but the
    GM-override escape hatch matches the v2.6.1 over-budget gate
    pattern (override clears strict-mode + paralysis alike)."""
    caelan = caelan_rested
    krieger = roster["Krieger Stonefist"]
    await _seed_battle(gm_client, [
        _make_combatant(caelan["name"], caelan["id"],
                        buffs=[PARALYZED_BUFF]),
        _make_combatant(krieger["name"], krieger["id"]),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": caelan["id"],
            "attack_index": 0,
            "target_combatant_id": f"tok_inc_{krieger['id']}",
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text


async def test_non_incapacitated_caster_attack_succeeds(
    gm_client, caelan_rested, roster,
):
    """Caelan has no incapacitating buff; /attack proceeds normally.
    Confirms the gate is silent in the common case."""
    caelan = caelan_rested
    krieger = roster["Krieger Stonefist"]
    await _seed_battle(gm_client, [
        _make_combatant(caelan["name"], caelan["id"]),  # No buffs.
        _make_combatant(krieger["name"], krieger["id"]),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": caelan["id"],
            "attack_index": 0,
            "target_combatant_id": f"tok_inc_{krieger['id']}",
        },
    )
    assert resp.status_code == 200, resp.text
