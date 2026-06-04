"""v2.99.156 — /use_turn_the_unholy endpoint tests.

Turn the Unholy is the Paladin Oath of Devotion Lv 3+ Channel
Divinity option (PHB p.86): fiends/undead within 30 ft make a
WIS save or are turned for 1 minute. The v2.14.3 audit-only
/use_feature path already exists for the Channel Divinity gate
+ announce. v2.99.156 adds the per-target mechanical layer:
takes the post-save failed-target list, installs the `turned`
buff on each, decrements the channel-divinity resource.

v1 simplification: the GM is responsible for resolving the WIS
saves and supplying the failed-target list. Auto-creature-type
filtering + per-target save resolution are filed.

Tests:
  - happy path (Caelan + 1 target) → 200; turned buff installs
    on target; channel-divinity decrements
  - empty target list → 400
  - second use without rest → 409 not_enough_uses
  - missing character_id → 400
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _mkc(cid, char_id=None, name="X", speed_walk=30):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": 50, "hp_max": 50,
        "speed_walk": speed_walk,
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False,
                    "movement": 0, "dash_bonus_ft": 0},
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1,
              "active": True},
    )


async def _get_buff_keys(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    return {(b or {}).get("key") for b in resp.json().get("buffs") or []}


@pytest_asyncio.fixture
async def caelan_rested(gm_client, roster):
    """Short-rest Caelan so channel-divinity resource is fresh."""
    caelan = roster["Sir Caelan Lightbringer"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/rest",
        json={"type": "short"},
    )
    return caelan


async def test_use_turn_the_unholy_happy_path(
    gm_client, gm_ws, caelan_rested, roster,
):
    """Caelan turns Krieger (acting as fiend/undead target per
    GM adjudication) → 200; turned buff installs; CD decrements;
    WS audit names the target.
    """
    caelan = caelan_rested
    krieger = roster["Krieger Stonefist"]
    cae_tok = f"tok_ttu_cae_{caelan['id']}"
    kri_tok = f"tok_ttu_kri_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(cae_tok, caelan["id"], name=caelan["name"]),
        _mkc(kri_tok, krieger["id"], name=krieger["name"], speed_walk=40),
    ])
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_turn_the_unholy",
        json={
            "character_id": caelan["id"],
            "target_combatant_ids": [kri_tok],
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["duration_rounds"] == 10
    assert data["uses_remaining"] == 0
    affected = data.get("affected") or []
    assert len(affected) == 1
    assert affected[0]["combatant_id"] == kri_tok
    assert affected[0]["installed"] is True
    # Krieger has the turned buff.
    kri_keys = await _get_buff_keys(gm_client, krieger["id"])
    assert "turned" in kri_keys
    msg = await gm_ws.wait_for("feature_used")
    bd = msg["data"]
    assert bd.get("source") == "turn-the-unholy"
    assert kri_tok in (bd.get("affected_combatant_ids") or [])


async def test_use_turn_the_unholy_empty_target_list_400(
    gm_client, caelan_rested,
):
    """Empty target_combatant_ids → 400."""
    caelan = caelan_rested
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_turn_the_unholy",
        json={
            "character_id": caelan["id"],
            "target_combatant_ids": [],
        },
    )
    assert resp.status_code == 400, resp.text


async def test_use_turn_the_unholy_second_use_409(
    gm_client, caelan_rested, roster,
):
    """Two consecutive uses without rest → second is 409
    not_enough_uses (1/short-rest gate, channel-divinity).
    """
    caelan = caelan_rested
    krieger = roster["Krieger Stonefist"]
    cae_tok = f"tok_ttu_2x_cae_{caelan['id']}"
    kri_tok = f"tok_ttu_2x_kri_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(cae_tok, caelan["id"], name=caelan["name"]),
        _mkc(kri_tok, krieger["id"], name=krieger["name"], speed_walk=40),
    ])
    cast1 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_turn_the_unholy",
        json={
            "character_id": caelan["id"],
            "target_combatant_ids": [kri_tok],
        },
    )
    assert cast1.status_code == 200, cast1.text
    cast2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_turn_the_unholy",
        json={
            "character_id": caelan["id"],
            "target_combatant_ids": [kri_tok],
        },
    )
    assert cast2.status_code == 409, cast2.text
    data = cast2.json()
    assert data.get("error") == "not_enough_uses"
    assert data.get("resource_key") == "channel-divinity"


async def test_use_turn_the_unholy_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_turn_the_unholy",
        json={"target_combatant_ids": ["x"]},
    )
    assert resp.status_code == 400, resp.text
