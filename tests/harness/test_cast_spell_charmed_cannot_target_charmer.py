"""v2.391.0 — /cast_spell rejects 409 when the caster is charmed by the target.

Mirror of the v2.390.0 /attack gate, applied to /cast_spell. Closes
the filed follow-up from v2.390.1/v2.390.2 — the
Charmed-cannot-target-charmer rule now covers the two PC action
endpoints that can target a creature (/attack + /cast_spell).
/use_feature is mostly self-targeted (Action Surge, Lay on Hands,
Channel Divinity) so the mirror is moot there.

Note: the gate fires for ALL spells — RAW technically allows
beneficial-spell targeting (e.g. Cure Wounds on the charmer), but
v1 treats "target the charmer" uniformly. body.get("override") is
the GM escape hatch for the beneficial-cast case.

Tests:
  - Caelan is charmed by Pip; calling /cast_spell with Pip as the
    target → 409 charmed_cannot_target_charmer.
  - Same setup with override → 200.
  - Caelan attacks a third party (Krieger) → 200 (gate is
    target-specific).
"""
from __future__ import annotations

import pytest_asyncio

from .conftest import CAMPAIGN_ID


CAELAN_BLESS_INDEX = 0  # Caelan's spell list (demo_seed.py:~1847).


def _make_combatant(name, char_id, hp=50, init=10, buffs=None):
    return {
        "id": f"tok_csc_{char_id}",
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
async def caelan_rested(gm_client, roster):
    caelan = roster["Sir Caelan Lightbringer"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/rest",
        json={"type": "long"},
    )
    # Drop any pre-existing concentration.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": caelan["id"], "key": "bless"},
    )
    return caelan


async def test_charmed_caster_targeting_charmer_returns_409(
    gm_client, caelan_rested, roster,
):
    """Caelan is charmed by Pip; calling /cast_spell with Pip as
    the target → 409 charmed_cannot_target_charmer."""
    caelan = caelan_rested
    pip = roster["Pip Quickfingers"]
    await _seed_battle(gm_client, [
        _make_combatant(caelan["name"], caelan["id"],
                        buffs=[_charmed_buff(pip["id"])]),
        _make_combatant(pip["name"], pip["id"]),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": caelan["id"],
            "spell_index": CAELAN_BLESS_INDEX,
            "slot_level": 1,
            "class_slug": "paladin",
            "target_combatant_ids": [f"tok_csc_{pip['id']}"],
            "override_range": True,
        },
    )
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body.get("error") == "charmed_cannot_target_charmer"
    assert body.get("char_name") == caelan["name"]
    assert body.get("source") == "cast_spell"
    assert body.get("target_combatant_id") == f"tok_csc_{pip['id']}"


async def test_charmed_caster_targeting_charmer_with_override_succeeds(
    gm_client, caelan_rested, roster,
):
    """Same setup with override → 200 (GM bypass)."""
    caelan = caelan_rested
    pip = roster["Pip Quickfingers"]
    await _seed_battle(gm_client, [
        _make_combatant(caelan["name"], caelan["id"],
                        buffs=[_charmed_buff(pip["id"])]),
        _make_combatant(pip["name"], pip["id"]),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": caelan["id"],
            "spell_index": CAELAN_BLESS_INDEX,
            "slot_level": 1,
            "class_slug": "paladin",
            "target_combatant_ids": [f"tok_csc_{pip['id']}"],
            "override": True,
            "override_range": True,
        },
    )
    assert resp.status_code == 200, resp.text
    # Cleanup the Bless buff that just landed on Pip.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": pip["id"], "key": "bless"},
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": caelan["id"], "key": "bless"},
    )


async def test_charmed_caster_targeting_third_party_succeeds(
    gm_client, caelan_rested, roster,
):
    """Caelan is charmed by Pip; casting on Krieger (third party) is
    fine — only the charmer is off-limits."""
    caelan = caelan_rested
    pip = roster["Pip Quickfingers"]
    krieger = roster["Krieger Stonefist"]
    await _seed_battle(gm_client, [
        _make_combatant(caelan["name"], caelan["id"],
                        buffs=[_charmed_buff(pip["id"])]),
        _make_combatant(pip["name"], pip["id"]),
        _make_combatant(krieger["name"], krieger["id"]),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": caelan["id"],
            "spell_index": CAELAN_BLESS_INDEX,
            "slot_level": 1,
            "class_slug": "paladin",
            "target_combatant_ids": [f"tok_csc_{krieger['id']}"],
            "override_range": True,
        },
    )
    assert resp.status_code == 200, resp.text
    # Cleanup.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": krieger["id"], "key": "bless"},
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": caelan["id"], "key": "bless"},
    )
