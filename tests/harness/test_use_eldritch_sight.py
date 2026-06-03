"""v2.99.138 — /use_eldritch_sight endpoint tests.

Eldritch Sight is a Warlock Lv 2+ Eldritch Invocation: cast
Detect Magic at will (PHB p.110). v1 ships the audit broadcast +
invocation gate only — the full magic-aura visualization layer is
filed (SimpleVTT doesn't have a "magic aura" map layer today).

Mirror of the v2.99.104 Mask of Many Faces / v2.99.131 Devil's
Sight pattern.

Tests:
  - happy path (Magnus has the invocation) → 200 + WS feature_used
    broadcast with `source: eldritch-sight` + `range_ft: 30` +
    `duration_rounds: 100` (10 min concentration)
  - missing invocation (Krieger Barbarian) → 409 missing_invocation
  - missing character_id → 400
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def test_use_eldritch_sight_happy_path(gm_client, gm_ws, roster):
    """Magnus has eldritch-invocation-eldritch-sight on his feats
    list. Endpoint returns 200 + emits the audit broadcast.
    """
    magnus = roster["Magnus Hexbinder"]
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_eldritch_sight",
        json={"character_id": magnus["id"]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["range_ft"] == 30
    assert data["duration_rounds"] == 100
    assert data["character_id"] == magnus["id"]
    msg = await gm_ws.wait_for("feature_used")
    bd = msg["data"]
    assert bd.get("source") == "eldritch-sight"
    assert bd.get("character_id") == magnus["id"]
    assert bd.get("range_ft") == 30


async def test_use_eldritch_sight_without_invocation_409(gm_client, roster):
    """Krieger (Barbarian) → 409 missing_invocation."""
    krieger = roster["Krieger Stonefist"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_eldritch_sight",
        json={"character_id": krieger["id"]},
    )
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert data.get("error") == "missing_invocation"
    assert data.get("invocation") == "eldritch-sight"


async def test_use_eldritch_sight_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_eldritch_sight",
        json={},
    )
    assert resp.status_code == 400, resp.text
