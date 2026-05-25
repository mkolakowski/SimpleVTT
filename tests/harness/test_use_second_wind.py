"""/api/campaign/{cid}/use_second_wind — Fighter Lv 1 feature tests.

v2.17.1: Second Wind shipped end-to-end. Garrik (Lv 7 Fighter
post-v2.49.237 bump for Remarkable Athlete, demo PC since v2.17.0)
has the resource counter at 1/1 short-rest refresh. The endpoint
rolls 1d10 + fighter_level (so 1d10+7 for Garrik → 8-17 HP) and
applies via _apply_hp_change.

Tests:
  - happy path: Garrik spends Second Wind, response carries rolled
    value + actual_healed + new HP; broadcasts fire
  - 409 out_of_uses (drain-loop)
  - 409 wrong-class (Pip is Rogue)
  - 400 missing character_id
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def garrik_full(gm_client, roster):
    """Long-rest Garrik to refill Second Wind + Action Surge counters
    before each test. Without this fixture other tests can deplete
    his counter and leave state ambiguous.
    """
    garrik = roster["Garrik Ironside"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/rest",
        json={"type": "long"},
    )
    return garrik


async def test_second_wind_happy_path(gm_client, gm_ws, garrik_full):
    """Garrik spends Second Wind. Asserts: 200 response, rolled value
    in [10, 19] for Lv 9 (1d10+9, v2.56.0 bump), actual_healed =
    min(rolled, hp_gap), feature_used + resource_update broadcasts
    fire.
    """
    garrik = garrik_full
    gm_ws.mark()  # discard the long-rest broadcasts
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_second_wind",
        json={"character_id": garrik["id"], "override": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["expression"] == "1d10+9"  # Lv 9 fighter (v2.56.0 bump for Indomitable)
    assert 10 <= data["rolled"] <= 19
    # Garrik starts at full HP (85/85 after the long rest, post-v2.56.0
    # bump from 67), so actual_healed = 0 (can't heal past max).
    assert data["actual_healed"] == 0
    assert data["hp"]["current"] == data["hp"]["max"]
    assert data["remaining"] == 0  # was 1, decremented

    msg = await gm_ws.wait_for("feature_used")
    assert msg["data"]["source"] == "second-wind"
    assert "Second Wind" in msg["data"]["feature_name"]
    # v2.43.0: heal_amount carries the actual HP delta (capped by max
    # HP). When Garrik starts at full HP it's 0; the field is still
    # present. heal_target_name is the caster (self-heal).
    assert "heal_amount" in msg["data"]
    assert msg["data"]["heal_target_name"] == garrik["name"]
    assert msg["data"]["heal_amount"] == data["actual_healed"]

    ru_msg = await gm_ws.wait_for("resource_update")
    assert ru_msg["data"]["key"] == "second-wind"
    assert ru_msg["data"]["current"] == 0


async def test_second_wind_out_of_uses(gm_client, garrik_full):
    """Drain Second Wind to 0 then attempt again — 409 out_of_uses."""
    garrik = garrik_full
    # Spend the one use.
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_second_wind",
        json={"character_id": garrik["id"], "override": True},
    )
    assert resp.status_code == 200, resp.text

    # Second attempt — out of uses.
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_second_wind",
        json={"character_id": garrik["id"], "override": True},
    )
    assert resp.status_code == 409
    assert resp.json().get("error") == "out_of_uses"


async def test_second_wind_wrong_class(gm_client, roster):
    """Pip is a Rogue — no Fighter level. Endpoint returns 409
    "Second Wind requires Fighter level 1+".
    """
    pip = roster["Pip Quickfingers"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_second_wind",
        json={"character_id": pip["id"], "override": True},
    )
    assert resp.status_code == 409
    detail = resp.json().get("detail", "")
    assert "Fighter" in detail


async def test_second_wind_missing_character_id(gm_client):
    """Missing character_id returns 400."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_second_wind",
        json={},
    )
    assert resp.status_code == 400
