"""v2.99.146 — /use_eyes_of_the_rune_keeper endpoint tests.

Eyes of the Rune Keeper is a Warlock Lv 2+ Eldritch Invocation:
read all writing (PHB p.110). v1 ships the audit broadcast +
invocation gate only — there's no "writing layer" in SimpleVTT
today.

Mirror of the v2.99.138/.141/.143/.145 audit-only pattern.

Tests:
  - happy path (Magnus has the invocation) → 200 + WS feature_used
    broadcast with `source: eyes-of-the-rune-keeper`
  - missing invocation (Krieger Barbarian) → 409 missing_invocation
  - missing character_id → 400
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def test_use_eyes_of_the_rune_keeper_happy_path(
    gm_client, gm_ws, roster,
):
    """Magnus has the invocation. Endpoint returns 200 + emits the
    audit broadcast.
    """
    magnus = roster["Magnus Hexbinder"]
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_eyes_of_the_rune_keeper",
        json={"character_id": magnus["id"]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["character_id"] == magnus["id"]
    msg = await gm_ws.wait_for("feature_used")
    bd = msg["data"]
    assert bd.get("source") == "eyes-of-the-rune-keeper"
    assert bd.get("character_id") == magnus["id"]


async def test_use_eyes_of_the_rune_keeper_without_invocation_409(
    gm_client, roster,
):
    """Krieger (Barbarian) → 409 missing_invocation."""
    krieger = roster["Krieger Stonefist"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_eyes_of_the_rune_keeper",
        json={"character_id": krieger["id"]},
    )
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert data.get("error") == "missing_invocation"
    assert data.get("invocation") == "eyes-of-the-rune-keeper"


async def test_use_eyes_of_the_rune_keeper_missing_character_id_400(
    gm_client,
):
    """Missing character_id → 400."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_eyes_of_the_rune_keeper",
        json={},
    )
    assert resp.status_code == 400, resp.text
