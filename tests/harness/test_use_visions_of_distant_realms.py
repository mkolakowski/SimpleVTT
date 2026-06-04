"""v2.99.152 — /use_visions_of_distant_realms endpoint tests.

Visions of Distant Realms is a Warlock Lv 15+ Eldritch
Invocation: cast Arcane Eye at will (PHB p.111). v1 ships the
audit broadcast + invocation gate only — there's no Arcane Eye
sensor token / map exploration overlay in SimpleVTT today.

**20th and final SRD Eldritch Invocation** for Magnus's roster
— closes the v2.99.95-onward invocation series. Magnus's
roster is now at 20/20.

Mirror of v2.99.138/.141/.145/.146/.147 audit-only pattern.

Tests:
  - happy path (Magnus has the invocation) → 200 + WS
    feature_used broadcast with `source:
    visions-of-distant-realms` + `duration_rounds: 600` +
    `move_per_turn_ft: 30`
  - missing invocation (Krieger Barbarian) → 409
    missing_invocation
  - missing character_id → 400
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def test_use_visions_of_distant_realms_happy_path(
    gm_client, gm_ws, roster,
):
    """Magnus has the invocation. Endpoint returns 200 + emits
    the audit broadcast with the 1-hour duration + 30 ft/turn
    move budget.
    """
    magnus = roster["Magnus Hexbinder"]
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_visions_of_distant_realms",
        json={"character_id": magnus["id"]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["duration_rounds"] == 600
    assert data["move_per_turn_ft"] == 30
    assert data["character_id"] == magnus["id"]
    msg = await gm_ws.wait_for("feature_used")
    bd = msg["data"]
    assert bd.get("source") == "visions-of-distant-realms"
    assert bd.get("character_id") == magnus["id"]
    assert bd.get("duration_rounds") == 600
    assert bd.get("move_per_turn_ft") == 30


async def test_use_visions_of_distant_realms_without_invocation_409(
    gm_client, roster,
):
    """Krieger (Barbarian) → 409 missing_invocation."""
    krieger = roster["Krieger Stonefist"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_visions_of_distant_realms",
        json={"character_id": krieger["id"]},
    )
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert data.get("error") == "missing_invocation"
    assert data.get("invocation") == "visions-of-distant-realms"


async def test_use_visions_of_distant_realms_missing_character_id_400(
    gm_client,
):
    """Missing character_id → 400."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_visions_of_distant_realms",
        json={},
    )
    assert resp.status_code == 400, resp.text
