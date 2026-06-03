"""v2.99.147 — /use_whispers_of_the_grave endpoint tests.

Whispers of the Grave is a Warlock Lv 9+ Eldritch Invocation:
cast Speak with Dead at will (PHB p.111). v1 ships the audit
broadcast + invocation gate only — there's no corpse-
interrogation dialog layer in SimpleVTT today.

Mirror of v2.99.138/.141/.145/.146 audit-only pattern.

Tests:
  - happy path (Magnus has the invocation) → 200 + WS feature_used
    broadcast with `source: whispers-of-the-grave` +
    `duration_rounds: 100` + `questions: 5`
  - missing invocation (Krieger Barbarian) → 409 missing_invocation
  - missing character_id → 400
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def test_use_whispers_of_the_grave_happy_path(
    gm_client, gm_ws, roster,
):
    """Magnus has the invocation. Endpoint returns 200 + emits the
    audit broadcast with the question count + duration.
    """
    magnus = roster["Magnus Hexbinder"]
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_whispers_of_the_grave",
        json={"character_id": magnus["id"]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["duration_rounds"] == 100
    assert data["questions"] == 5
    assert data["character_id"] == magnus["id"]
    msg = await gm_ws.wait_for("feature_used")
    bd = msg["data"]
    assert bd.get("source") == "whispers-of-the-grave"
    assert bd.get("character_id") == magnus["id"]
    assert bd.get("questions") == 5
    assert bd.get("duration_rounds") == 100


async def test_use_whispers_of_the_grave_without_invocation_409(
    gm_client, roster,
):
    """Krieger (Barbarian) → 409 missing_invocation."""
    krieger = roster["Krieger Stonefist"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_whispers_of_the_grave",
        json={"character_id": krieger["id"]},
    )
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert data.get("error") == "missing_invocation"
    assert data.get("invocation") == "whispers-of-the-grave"


async def test_use_whispers_of_the_grave_missing_character_id_400(
    gm_client,
):
    """Missing character_id → 400."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_whispers_of_the_grave",
        json={},
    )
    assert resp.status_code == 400, resp.text
