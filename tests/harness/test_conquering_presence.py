"""v2.99.247 — Conquest Paladin: Conquering Presence CD (Phase H.2 third oath).

Phase H.2 third non-Devotion Paladin oath. RAW XGE p.37:
Conquest Paladin Lv 3+ action CD — AOE: target each creature
within 30 ft (caster picks), Wis save DC 8 + prof + CHA or
Frightened 1 minute (repeat save each end of turn).

v1 ships:
  - /use_conquering_presence: validates Conquest Paladin Lv 3+
    + channel-divinity resource current >= 1 + non-empty target
    list + each target in battle + action chip. Decrements CD,
    marks chip, computes DC, broadcasts.

Sir Caelan Lightbringer is the demo fixture. Tests PATCH his
subclass to "Oath of Conquest" + seed Caelan + 2 Bandits in
battle. Caelan Lv 8 CHA 16 → DC 14.

Tests:
  - Happy 2 targets → CD 1 → 0, DC 14, broadcast.
  - Empty target list → 400.
  - Unknown target in list → 404.
  - Out of CD → 409.
  - Wrong subclass → 409.
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


def _cp_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "conquering-presence"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


def _cd_resource(current: int, maximum: int) -> dict:
    return {
        "key": "channel-divinity",
        "name": "Channel Divinity",
        "current": current, "max": maximum, "reset": "short",
        "source": "paladin Lv 3",
        "class_slug": "paladin",
        "subclass_slug": "conquest",
        "desc": "Channel a domain effect (Conquering Presence, Guided Strike). One use per short rest.",
        "manual": False,
    }


@pytest_asyncio.fixture
async def caelan_conquest_with_bandits(gm_client, roster):
    """PATCH Caelan to Conquest + reset CD + seed battle with 2 Bandits."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {
            "subclass": "Oath of Conquest",
            "resources": [_cd_resource(1, 1)],
        },
        class_slug="paladin",
    )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_cc_{caelan['id']}",
             "char_id": caelan["id"], "name": caelan["name"],
             "initiative": 12, "hp_current": 60, "hp_max": 60,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": "tok_bnd_a",
             "char_id": None,
             "name": "Bandit Alpha", "initiative": 8,
             "hp_current": 50, "hp_max": 50,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": "tok_bnd_b",
             "char_id": None,
             "name": "Bandit Beta", "initiative": 6,
             "hp_current": 50, "hp_max": 50,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    try:
        yield caelan
    finally:
        await _patch_sheet(
            gm_client, caelan["id"],
            {"subclass": "Oath of Devotion", "resources": []},
            class_slug="paladin",
        )


async def test_use_cp_happy(
    gm_client, gm_ws, caelan_conquest_with_bandits,
):
    """Conquest Caelan targets 2 bandits → CD 1 → 0, DC 14."""
    caelan = caelan_conquest_with_bandits
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_conquering_presence",
        json={
            "character_id": caelan["id"],
            "target_combatant_ids": ["tok_bnd_a", "tok_bnd_b"],
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["save_dc"] == 14
    assert data["uses_remaining"] == 0
    assert len(data["target_combatant_ids"]) == 2
    await asyncio.sleep(0.3)
    feats = _cp_broadcasts(gm_ws, caelan["id"])
    assert feats


async def test_use_cp_empty_target_list(
    gm_client, caelan_conquest_with_bandits,
):
    """Empty list → 400."""
    caelan = caelan_conquest_with_bandits
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_conquering_presence",
        json={
            "character_id": caelan["id"],
            "target_combatant_ids": [],
            "override": True,
        },
    )
    assert r.status_code == 400, r.text


async def test_use_cp_unknown_target(
    gm_client, caelan_conquest_with_bandits,
):
    """One unknown target → 404."""
    caelan = caelan_conquest_with_bandits
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_conquering_presence",
        json={
            "character_id": caelan["id"],
            "target_combatant_ids": ["tok_bnd_a", "tok_ghost"],
            "override": True,
        },
    )
    assert r.status_code == 404, r.text


async def test_use_cp_out_of_cd(
    gm_client, caelan_conquest_with_bandits,
):
    """CD current=0 → 409."""
    caelan = caelan_conquest_with_bandits
    await _patch_sheet(
        gm_client, caelan["id"],
        {"resources": [_cd_resource(0, 1)]},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_conquering_presence",
        json={
            "character_id": caelan["id"],
            "target_combatant_ids": ["tok_bnd_a"],
            "override": True,
        },
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "out_of_uses"


async def test_use_cp_wrong_subclass(
    gm_client, roster,
):
    """Default Caelan (Devotion) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_conquering_presence",
        json={
            "character_id": caelan["id"],
            "target_combatant_ids": ["tok_bnd_a"],
            "override": True,
        },
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
