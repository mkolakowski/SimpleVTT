"""/api/campaign/{cid}/use_wholeness_of_body — Way of the Open Hand Lv 6.

v2.49.227: Wholeness of Body shipped end-to-end. Kael Brightleaf (Lv 6
Monk, Way of the Open Hand — bumped from Lv 5 to 6 in the same release)
has the resource counter at 1/1 long-rest refresh. The endpoint applies
3 × monk_level HP via _apply_hp_change (deterministic, no roll) and
marks the action slot.

Tests:
  - happy path: Kael spends Wholeness of Body, response carries
    rolled=3*lv + actual_healed + new HP; feature_used + resource_update
    broadcasts fire
  - 409 out_of_uses (drain loop)
  - 409 wrong-class (Pip is Rogue)
  - 400 missing character_id
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def kael_full(gm_client, roster):
    """Long-rest Kael to refill Wholeness of Body + Ki counters
    before each test. Without this fixture other tests can deplete
    his counters and leave state ambiguous.
    """
    kael = roster["Kael Brightleaf"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{kael['id']}/rest",
        json={"type": "long"},
    )
    return kael


async def test_wholeness_of_body_happy_path(gm_client, gm_ws, kael_full):
    """Kael spends Wholeness of Body. Asserts: 200 response,
    rolled = 3 × monk_level (21 at Lv 7 post-v2.49.229),
    actual_healed = min(rolled, hp_gap), counter decrements,
    feature_used + resource_update broadcasts fire.
    """
    kael = kael_full
    gm_ws.mark()  # discard the long-rest broadcasts
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_wholeness_of_body",
        json={"character_id": kael["id"], "override": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    # Lv 7 monk → 3 × 7 = 21 HP regain. Deterministic (no roll).
    assert data["rolled"] == 21
    # Kael starts at full HP (52/52 after the long rest), so
    # actual_healed = 0 (can't heal past max). The endpoint still
    # decrements the counter — burning the use at full HP is wasteful
    # but the server doesn't gate on it (matches the RAW: spending the
    # action commits the use).
    assert data["actual_healed"] == 0
    assert data["hp"]["current"] == data["hp"]["max"] == 52
    assert data["remaining"] == 0  # was 1, decremented
    assert data["max"] == 1

    msg = await gm_ws.wait_for("feature_used")
    assert msg["data"]["source"] == "wholeness-of-body"
    assert "Wholeness of Body" in msg["data"]["feature_name"]
    assert msg["data"]["heal_target_name"] == kael["name"]
    assert msg["data"]["heal_amount"] == data["actual_healed"]
    # feature_desc carries the rolled total + level annotation.
    assert "21" in msg["data"]["feature_desc"]
    assert "Lv 7" in msg["data"]["feature_desc"]

    ru_msg = await gm_ws.wait_for("resource_update")
    assert ru_msg["data"]["key"] == "wholeness-of-body"
    assert ru_msg["data"]["current"] == 0
    assert ru_msg["data"]["max"] == 1


async def test_wholeness_of_body_out_of_uses(gm_client, kael_full):
    """Drain Wholeness of Body to 0 then attempt again — 409
    out_of_uses.
    """
    kael = kael_full
    # Spend the one use.
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_wholeness_of_body",
        json={"character_id": kael["id"], "override": True},
    )
    assert resp.status_code == 200, resp.text

    # Second attempt — out of uses.
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_wholeness_of_body",
        json={"character_id": kael["id"], "override": True},
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body.get("error") == "out_of_uses"
    assert body.get("label") == "Wholeness of Body"


async def test_wholeness_of_body_wrong_class(gm_client, roster):
    """Pip is a Rogue — endpoint returns 409 with error=wrong_class."""
    pip = roster["Pip Quickfingers"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_wholeness_of_body",
        json={"character_id": pip["id"], "override": True},
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body.get("error") == "wrong_class"
    assert body.get("expected") == "monk"
    assert body.get("got") == "rogue"


async def test_wholeness_of_body_missing_character_id(gm_client):
    """Missing character_id returns 400."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_wholeness_of_body",
        json={},
    )
    assert resp.status_code == 400
