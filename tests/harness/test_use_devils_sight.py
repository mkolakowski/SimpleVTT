"""v2.99.131 — /use_devils_sight endpoint tests.

Devil's Sight is a Warlock Lv 2+ Eldritch Invocation: 120 ft sight
in magical+nonmagical darkness (PHB p.110). v1 ships the audit
broadcast + invocation gate only — the full vision/lighting engine
that respects this marker is filed for a future commit.

Tests mirror the v2.99.104 Mask of Many Faces shape:
  - happy path (Magnus has the invocation) → 200 + WS feature_used
    broadcast with `source: devils-sight` + `range_ft: 120`
  - missing invocation (Krieger Barbarian → no invocation) → 409
    missing_invocation
  - missing character_id → 400
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def test_use_devils_sight_happy_path(gm_client, gm_ws, roster):
    """Magnus has eldritch-invocation-devils-sight on his feats list.
    Endpoint returns 200 + broadcasts feature_used with the right
    source + range_ft.
    """
    magnus = roster["Magnus Hexbinder"]
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_devils_sight",
        json={"character_id": magnus["id"]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["range_ft"] == 120
    assert data["character_id"] == magnus["id"]
    # WS broadcast.
    msg = await gm_ws.wait_for("feature_used")
    bd = msg["data"]
    assert bd.get("source") == "devils-sight"
    assert bd.get("character_id") == magnus["id"]
    assert bd.get("range_ft") == 120


async def test_use_devils_sight_without_invocation_409(gm_client, roster):
    """Krieger (Barbarian) has no Warlock invocations → 409
    missing_invocation.
    """
    krieger = roster["Krieger Stonefist"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_devils_sight",
        json={"character_id": krieger["id"]},
    )
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert data.get("error") == "missing_invocation"
    assert data.get("invocation") == "devils-sight"


async def test_use_devils_sight_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_devils_sight",
        json={},
    )
    assert resp.status_code == 400, resp.text
