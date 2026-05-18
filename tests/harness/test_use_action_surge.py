"""/api/campaign/{cid}/use_action_surge — Fighter Lv 2 feature tests.

v2.17.2: Action Surge shipped end-to-end. Garrik (Lv 5 Champion
Fighter, demo PC since v2.17.0) has the resource counter at 1/1
short-rest refresh. The endpoint decrements the counter, refunds
the action chip via _mark_battle_economy(..., used=False), and
broadcasts feature_used + resource_update + economy_update.

Tests:
  - happy path: Garrik spends Action Surge; counter drops + action
    chip clears + economy_update broadcasts
  - chip-refund: pre-mark Garrik's action chip via PUT /battle,
    then fire Action Surge → assert the chip clears
  - 409 out_of_uses (drain-loop)
  - 409 wrong-class (Pip is Rogue)
  - 400 missing character_id

Mirrors the test_transform_over_budget_flag pattern for injecting
battle state via PUT /battle.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def garrik_fresh(gm_client, roster):
    """Long-rest Garrik to refill Action Surge + Second Wind counters."""
    garrik = roster["Garrik Ironside"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/rest",
        json={"type": "long"},
    )
    return garrik


async def test_action_surge_happy_path(gm_client, gm_ws, garrik_fresh):
    """Garrik spends Action Surge. No battle state injected so the
    chip-refund is a no-op (the helper skips when no combatants
    exist), but the counter decrement + broadcasts still fire.
    """
    garrik = garrik_fresh
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_action_surge",
        json={"character_id": garrik["id"]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["remaining"] == 0  # was 1, decremented
    assert data["action_chip_refunded"] is True

    msg = await gm_ws.wait_for("feature_used")
    assert msg["data"]["source"] == "action-surge"
    assert "Action Surge" in msg["data"]["feature_name"]

    ru_msg = await gm_ws.wait_for("resource_update")
    assert ru_msg["data"]["key"] == "action-surge"
    assert ru_msg["data"]["current"] == 0


async def test_action_surge_refunds_action_chip(gm_client, gm_ws, garrik_fresh):
    """Inject battle state with Garrik's action chip pre-marked, then
    fire Action Surge. Assert the economy_update broadcast fires with
    used=False, indicating the chip was refunded.

    Mirrors the test_transform_over_budget_flag pattern from v2.14.6.
    """
    garrik = garrik_fresh
    pre_state = {
        "combatants": [
            {
                "char_id": garrik["id"],
                "name": garrik["name"],
                "init": 19,
                "economy": {
                    "action": True,  # pre-marked — Garrik already swung this turn
                    "bonus": False,
                    "reaction": False,
                    "movement": 0,
                },
            }
        ],
        "round": 1,
        "active_index": 0,
    }
    resp = await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle", json=pre_state,
    )
    assert resp.status_code == 200, resp.text
    gm_ws.mark()  # discard the battle_update broadcast

    try:
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_action_surge",
            json={"character_id": garrik["id"]},
        )
        assert resp.status_code == 200, resp.text

        # economy_update broadcast: slot=action, used=False (refund)
        eu_msg = await gm_ws.wait_for("economy_update")
        assert eu_msg["data"]["character_id"] == garrik["id"]
        assert eu_msg["data"]["slot"] == "action"
        assert eu_msg["data"]["used"] is False  # refunded
    finally:
        # Clear battle state for subsequent tests.
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={"combatants": [], "round": 0, "active_index": 0},
        )


async def test_action_surge_out_of_uses(gm_client, garrik_fresh):
    """Spend the one use then attempt again — 409 out_of_uses."""
    garrik = garrik_fresh
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_action_surge",
        json={"character_id": garrik["id"]},
    )
    assert resp.status_code == 200, resp.text

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_action_surge",
        json={"character_id": garrik["id"]},
    )
    assert resp.status_code == 409
    assert resp.json().get("error") == "out_of_uses"


async def test_action_surge_wrong_class(gm_client, roster):
    """Pip is a Rogue — no Fighter level → 409 'Fighter level 2+'."""
    pip = roster["Pip Quickfingers"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_action_surge",
        json={"character_id": pip["id"]},
    )
    assert resp.status_code == 409
    detail = resp.json().get("detail", "")
    assert "Fighter" in detail


async def test_action_surge_missing_character_id(gm_client):
    """Missing character_id returns 400."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_action_surge",
        json={},
    )
    assert resp.status_code == 400
