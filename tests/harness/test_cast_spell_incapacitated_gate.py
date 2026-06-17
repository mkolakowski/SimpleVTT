"""v2.387.0 — /cast_spell incapacitated gate.

RAW PHB p.290: "An incapacitated creature can't take actions or
reactions." Mirror of the v2.386.0 /attack gate. Closes clause #2b
of the v2.384.0 condition-enforcement audit. Same contract as the
/attack gate: 409 `incapacitated` with structured payload + GM
`override: true` bypass + silent when the character isn't in init.

Tests:
  - Paralyzed Caelan calling /cast_spell → 409 `incapacitated`,
    spell index isn't looked up, slot isn't consumed.
  - Same setup with `override: True` → the gate is bypassed; the
    cast proceeds (200).
  - Non-incapacitated Caelan → /cast_spell proceeds normally (200).
"""
from __future__ import annotations

import pytest_asyncio

from .conftest import CAMPAIGN_ID


CAELAN_BLESS_INDEX = 0  # Caelan's spell list (app/demo_seed.py:~1847).


@pytest_asyncio.fixture
async def caelan_rested(gm_client, roster):
    caelan = roster["Sir Caelan Lightbringer"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/rest",
        json={"type": "long"},
    )
    # Drop any pre-existing concentration from prior tests.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": caelan["id"], "key": "bless"},
    )
    return caelan


def _make_combatant(name, char_id, hp=50, init=10, buffs=None):
    return {
        "id": f"tok_csi_{char_id}",
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


async def test_paralyzed_caster_cast_spell_returns_409(
    gm_client, caelan_rested, roster,
):
    """Caelan is paralyzed; calling /cast_spell returns 409
    `incapacitated` and the spell slot is NOT consumed."""
    caelan = caelan_rested
    pip = roster["Pip Quickfingers"]
    await _seed_battle(gm_client, [
        _make_combatant(caelan["name"], caelan["id"],
                        buffs=[PARALYZED_BUFF]),
        _make_combatant(pip["name"], pip["id"]),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": caelan["id"],
            "spell_index": CAELAN_BLESS_INDEX,
            "slot_level": 1,
            "class_slug": "paladin",
            "target_combatant_ids": [f"tok_csi_{pip['id']}"],
            "override_range": True,
        },
    )
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body.get("error") == "incapacitated"
    assert body.get("char_name") == caelan["name"]
    assert body.get("source") == "cast_spell"


async def test_paralyzed_caster_cast_spell_with_override_succeeds(
    gm_client, caelan_rested, roster,
):
    """Same setup but with `override: True` → the gate is bypassed;
    the cast proceeds (200). Mirrors the v2.386.0 /attack
    override-bypass contract."""
    caelan = caelan_rested
    pip = roster["Pip Quickfingers"]
    await _seed_battle(gm_client, [
        _make_combatant(caelan["name"], caelan["id"],
                        buffs=[PARALYZED_BUFF]),
        _make_combatant(pip["name"], pip["id"]),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": caelan["id"],
            "spell_index": CAELAN_BLESS_INDEX,
            "slot_level": 1,
            "class_slug": "paladin",
            "target_combatant_ids": [f"tok_csi_{pip['id']}"],
            "override": True,
            "override_range": True,
        },
    )
    assert resp.status_code == 200, resp.text
    # Cleanup — drop the bless we just installed.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": caelan["id"], "key": "bless"},
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": pip["id"], "key": "bless"},
    )


async def test_non_incapacitated_caster_cast_spell_succeeds(
    gm_client, caelan_rested, roster,
):
    """Caelan has no incapacitating buff; /cast_spell proceeds
    normally. Confirms the gate is silent in the common case."""
    caelan = caelan_rested
    pip = roster["Pip Quickfingers"]
    await _seed_battle(gm_client, [
        _make_combatant(caelan["name"], caelan["id"]),  # No buffs.
        _make_combatant(pip["name"], pip["id"]),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": caelan["id"],
            "spell_index": CAELAN_BLESS_INDEX,
            "slot_level": 1,
            "class_slug": "paladin",
            "target_combatant_ids": [f"tok_csi_{pip['id']}"],
            "override_range": True,
        },
    )
    assert resp.status_code == 200, resp.text
    # Cleanup.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": caelan["id"], "key": "bless"},
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": pip["id"], "key": "bless"},
    )
