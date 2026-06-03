"""v2.99.145 — /use_beast_speech endpoint tests.

Beast Speech is a Warlock Lv 2+ Eldritch Invocation: cast Speak
with Animals at will (PHB p.110). v1 ships the audit broadcast
+ invocation gate only — there's no animal-NPC dialog layer in
SimpleVTT today.

Mirror of the v2.99.138 Eldritch Sight / v2.99.141 Ascendant
Step / v2.99.143 Beguiling Influence pattern.

Tests:
  - happy path (Magnus has the invocation) → 200 + WS feature_used
    broadcast with `source: beast-speech` + `duration_rounds: 100`
  - missing invocation (Krieger Barbarian) → 409 missing_invocation
  - missing character_id → 400
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def test_use_beast_speech_happy_path(gm_client, gm_ws, roster):
    """Magnus has eldritch-invocation-beast-speech on his feats
    list. Endpoint returns 200 + emits the audit broadcast.
    """
    magnus = roster["Magnus Hexbinder"]
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_beast_speech",
        json={"character_id": magnus["id"]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["duration_rounds"] == 100
    assert data["character_id"] == magnus["id"]
    msg = await gm_ws.wait_for("feature_used")
    bd = msg["data"]
    assert bd.get("source") == "beast-speech"
    assert bd.get("character_id") == magnus["id"]
    assert bd.get("duration_rounds") == 100


async def test_use_beast_speech_without_invocation_409(gm_client, roster):
    """Krieger (Barbarian) → 409 missing_invocation."""
    krieger = roster["Krieger Stonefist"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_beast_speech",
        json={"character_id": krieger["id"]},
    )
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert data.get("error") == "missing_invocation"
    assert data.get("invocation") == "beast-speech"


async def test_use_beast_speech_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_beast_speech",
        json={},
    )
    assert resp.status_code == 400, resp.text
