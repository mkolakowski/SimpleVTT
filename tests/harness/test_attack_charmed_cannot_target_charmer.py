"""v2.390.0 — /attack rejects 409 when the attacker is charmed by the target.

RAW PHB p.290 Charmed clause 1: "A charmed creature can't attack the
charmer or target the charmer with harmful abilities or magical
effects." Closes clause #4 of the v2.384.0 condition-enforcement audit
— the final clause in the suggested per-clause shipping order.

The gate uses `_attacker_is_charmed_by_target` which walks the
attacker's combatant buff list for a `charmed` buff whose
`source_char_id` matches the target's char_id. Existing charmed-install
sites would need to populate `source_char_id` on the buff for the
gate to fire in real flows; that's a filed follow-up. v2.390.0 ships
the gate + the helper, validated by hand-seeded buffs.

Tests:
  - Pip attacks Caelan with a pre-seeded charmed buff sourced by
    Caelan → 409 charmed_cannot_target_charmer.
  - Same setup with `override: True` → 200 (gate bypassed).
  - Pip attacks a third party (Krieger) instead → 200 (gate is
    target-specific; only the charmer is off-limits).
  - Pip attacks Caelan but the charmed buff has no source_char_id
    → 200 (gate silently passes when the install site didn't
    populate the field).
"""
from __future__ import annotations

import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _make_combatant(name, char_id, hp=50, init=10, buffs=None):
    return {
        "id": f"tok_chrm_{char_id}",
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


def _charmed_buff(source_char_id):
    return {
        "key": "charmed",
        "name": "Charmed",
        "icon": "💚",
        "duration_rounds": 10,
        "concentration": False,
        "source_char_id": int(source_char_id),
    }


@pytest_asyncio.fixture
async def pip_rested(gm_client, roster):
    pip = roster["Pip Quickfingers"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/rest",
        json={"type": "long"},
    )
    return pip


async def test_charmed_attacker_targeting_charmer_returns_409(
    gm_client, pip_rested, roster,
):
    """Pip is charmed by Caelan; attempting to attack Caelan → 409
    charmed_cannot_target_charmer."""
    pip = pip_rested
    caelan = roster["Sir Caelan Lightbringer"]
    await _seed_battle(gm_client, [
        _make_combatant(pip["name"], pip["id"],
                        buffs=[_charmed_buff(caelan["id"])]),
        _make_combatant(caelan["name"], caelan["id"]),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": pip["id"],
            "attack_index": 0,
            "target_combatant_id": f"tok_chrm_{caelan['id']}",
        },
    )
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body.get("error") == "charmed_cannot_target_charmer"
    assert body.get("char_name") == pip["name"]
    assert body.get("source") == "attack"
    assert body.get("target_combatant_id") == f"tok_chrm_{caelan['id']}"


async def test_charmed_attacker_targeting_charmer_with_override_succeeds(
    gm_client, pip_rested, roster,
):
    """Same setup with `override: True` → 200 (GM bypass)."""
    pip = pip_rested
    caelan = roster["Sir Caelan Lightbringer"]
    await _seed_battle(gm_client, [
        _make_combatant(pip["name"], pip["id"],
                        buffs=[_charmed_buff(caelan["id"])]),
        _make_combatant(caelan["name"], caelan["id"]),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": pip["id"],
            "attack_index": 0,
            "target_combatant_id": f"tok_chrm_{caelan['id']}",
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text


async def test_charmed_attacker_targeting_third_party_succeeds(
    gm_client, pip_rested, roster,
):
    """Pip is charmed by Caelan; attacking Krieger (third party) is
    fine — only the charmer is off-limits."""
    pip = pip_rested
    caelan = roster["Sir Caelan Lightbringer"]
    krieger = roster["Krieger Stonefist"]
    await _seed_battle(gm_client, [
        _make_combatant(pip["name"], pip["id"],
                        buffs=[_charmed_buff(caelan["id"])]),
        _make_combatant(caelan["name"], caelan["id"]),
        _make_combatant(krieger["name"], krieger["id"]),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": pip["id"],
            "attack_index": 0,
            "target_combatant_id": f"tok_chrm_{krieger['id']}",
        },
    )
    assert resp.status_code == 200, resp.text


async def test_charmed_buff_without_source_char_id_passes_through(
    gm_client, pip_rested, roster,
):
    """Pip carries a charmed buff with NO source_char_id (mirrors the
    lair-action / environment-charm install paths that don't populate
    the field). The gate silently passes since it can't identify the
    charmer."""
    pip = pip_rested
    caelan = roster["Sir Caelan Lightbringer"]
    charmed_no_source = {
        "key": "charmed",
        "name": "Charmed (lair action)",
        "icon": "💚",
        "duration_rounds": 1,
        "concentration": False,
        # NO source_char_id field — the gate can't fire without it.
    }
    await _seed_battle(gm_client, [
        _make_combatant(pip["name"], pip["id"],
                        buffs=[charmed_no_source]),
        _make_combatant(caelan["name"], caelan["id"]),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": pip["id"],
            "attack_index": 0,
            "target_combatant_id": f"tok_chrm_{caelan['id']}",
        },
    )
    assert resp.status_code == 200, resp.text
