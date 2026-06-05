"""v2.99.244 — Order Domain Cleric: Voice of Authority (Phase H.1 eleventh + FINAL domain).

Phase H.1 final non-Life Cleric domain ship. RAW TCE p.39:
Order Cleric Lv 1+ — after casting a Lv 1+ spell that targets an
ally, the ally takes one weapon attack as a reaction.

v1 ships:
  - /use_voice_of_authority: validates Order Cleric Lv 1+ + ally
    in battle + non-self + ally's reaction chip. Marks the ALLY's
    reaction chip + broadcasts. Manual trigger; auto-offer via
    /cast_spell post-cast hook is filed.

Brother Tavik Stonebrow is the demo fixture. Tests PATCH his
subclass to "Order Domain" and seed Tavik + Pip + Caelan in a
battle.

Tests:
  - Happy: Tavik authorizes Caelan to attack Bandit → Caelan's
    reaction chip marked, broadcast.
  - Self-target → 409 self_targeting_not_allowed.
  - Unknown ally → 404.
  - Wrong subclass → 409.

This is the LAST of the 11 non-Life Cleric domains — H.1 is
COMPLETE.
"""
import asyncio
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _patch_sheet(gm_client, char_id, fields, class_slug=None):
    body = dict(fields)
    if class_slug:
        body["class_slug"] = class_slug
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json=body,
    )
    assert r.status_code == 200, r.text


def _voa_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "voice-of-authority"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def tavik_order_with_caelan(gm_client, roster):
    """PATCH Tavik to Order + seed Tavik + Caelan in a battle."""
    tavik = roster["Brother Tavik Stonebrow"]
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Order Domain"},
        class_slug="cleric",
    )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_to_{tavik['id']}",
             "char_id": tavik["id"], "name": tavik["name"],
             "initiative": 10, "hp_current": 55, "hp_max": 55,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": f"tok_co_{caelan['id']}",
             "char_id": caelan["id"], "name": caelan["name"],
             "initiative": 12, "hp_current": 60, "hp_max": 60,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    try:
        yield tavik, caelan
    finally:
        await _patch_sheet(
            gm_client, tavik["id"],
            {"subclass": "Life Domain"},
            class_slug="cleric",
        )


async def test_use_voa_ally_happy(
    gm_client, gm_ws, tavik_order_with_caelan,
):
    """Order Tavik authorizes Caelan's reaction attack vs Bandit."""
    tavik, caelan = tavik_order_with_caelan
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_voice_of_authority",
        json={
            "character_id": tavik["id"],
            "ally_combatant_id": f"tok_co_{caelan['id']}",
            "target_name": "Bandit Alpha",
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ally_char_id"] == caelan["id"]
    assert data["target_name"] == "Bandit Alpha"
    await asyncio.sleep(0.3)
    feats = _voa_broadcasts(gm_ws, tavik["id"])
    assert feats


async def test_use_voa_self_target(
    gm_client, tavik_order_with_caelan,
):
    """Targeting self → 409 (RAW: ally only)."""
    tavik, _ = tavik_order_with_caelan
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_voice_of_authority",
        json={
            "character_id": tavik["id"],
            "ally_combatant_id": f"tok_to_{tavik['id']}",
            "override": True,
        },
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "self_targeting_not_allowed"


async def test_use_voa_unknown_ally(
    gm_client, tavik_order_with_caelan,
):
    """Unknown ally → 404."""
    tavik, _ = tavik_order_with_caelan
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_voice_of_authority",
        json={
            "character_id": tavik["id"],
            "ally_combatant_id": "tok_ghost",
            "override": True,
        },
    )
    assert r.status_code == 404, r.text


async def test_use_voa_wrong_subclass(
    gm_client, roster,
):
    """Default Tavik (Life Domain) → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_voice_of_authority",
        json={
            "character_id": tavik["id"],
            "ally_combatant_id": f"tok_co_{caelan['id']}",
            "override": True,
        },
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
