"""v2.99.141 — /use_ascendant_step endpoint tests.

Ascendant Step is a Warlock Lv 9+ Eldritch Invocation: cast
Levitate on yourself at will (PHB p.110). v1 ships the audit
broadcast + invocation gate only — vertical-position map
plumbing is filed (SimpleVTT has no 2D-with-altitude layer
today).

Mirror of the v2.99.138 Eldritch Sight / v2.99.131 Devil's Sight
pattern.

Tests:
  - happy path (Magnus has the invocation) → 200 + WS feature_used
    broadcast with `source: ascendant-step` + `altitude_ft: 20` +
    `duration_rounds: 100` (10 min concentration)
  - missing invocation (Krieger Barbarian) → 409 missing_invocation
  - missing character_id → 400
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def test_use_ascendant_step_happy_path(gm_client, gm_ws, roster):
    """Magnus has eldritch-invocation-ascendant-step on his feats
    list. Endpoint returns 200 + emits the audit broadcast.
    """
    magnus = roster["Magnus Hexbinder"]
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_ascendant_step",
        json={"character_id": magnus["id"]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["altitude_ft"] == 20
    assert data["duration_rounds"] == 100
    assert data["character_id"] == magnus["id"]
    msg = await gm_ws.wait_for("feature_used")
    bd = msg["data"]
    assert bd.get("source") == "ascendant-step"
    assert bd.get("character_id") == magnus["id"]
    assert bd.get("altitude_ft") == 20


async def test_use_ascendant_step_without_invocation_409(gm_client, roster):
    """Krieger (Barbarian) → 409 missing_invocation."""
    krieger = roster["Krieger Stonefist"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_ascendant_step",
        json={"character_id": krieger["id"]},
    )
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert data.get("error") == "missing_invocation"
    assert data.get("invocation") == "ascendant-step"


async def test_use_ascendant_step_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_ascendant_step",
        json={},
    )
    assert resp.status_code == 400, resp.text
