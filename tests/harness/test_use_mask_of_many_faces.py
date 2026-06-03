"""v2.99.104 — /use_mask_of_many_faces endpoint tests.

Mask of Many Faces is a Warlock Lv 2+ Eldritch Invocation that
grants at-will Disguise Self (no slot cost). RAW (PHB p.111): "You
can cast Disguise Self at will, without expending a spell slot."

v1 ship: just the audit broadcast + the invocation gate. No
mechanical buff install — the spell's effect is purely illusory
(RAW: "this spell isn't actually a transformation of any kind").

Tests:
  - happy path (Magnus has the invocation) → 200 + WS feature_used
    broadcast with `source: mask-of-many-faces`
  - missing invocation (Krieger Barbarian → no invocation) → 409
  - missing character_id → 400
  - disguise_desc plumbs through to the broadcast
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def test_use_mask_of_many_faces_happy_path(
    gm_client, gm_ws, roster,
):
    """Magnus has eldritch-invocation-mask-of-many-faces on his
    feats list. Endpoint should 200 + emit feature_used.
    """
    magnus = roster["Magnus Hexbinder"]
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_mask_of_many_faces",
        json={
            "character_id": magnus["id"],
            "disguise_desc": "old human merchant",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["disguise_desc"] == "old human merchant"
    assert data["duration_rounds"] == 600  # 1 hour
    # WS broadcast.
    msg = await gm_ws.wait_for("feature_used")
    bd = msg["data"]
    assert bd.get("source") == "mask-of-many-faces"
    assert bd.get("character_id") == magnus["id"]
    assert bd.get("disguise_desc") == "old human merchant"


async def test_use_mask_of_many_faces_without_invocation_409(
    gm_client, roster,
):
    """Krieger (Barbarian) has no Warlock invocations. → 409
    missing_invocation.
    """
    krieger = roster["Krieger Stonefist"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_mask_of_many_faces",
        json={
            "character_id": krieger["id"],
            "disguise_desc": "innocent merchant",
        },
    )
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert data.get("error") == "missing_invocation"
    assert data.get("invocation") == "mask-of-many-faces"


async def test_use_mask_of_many_faces_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_mask_of_many_faces",
        json={"disguise_desc": "nobody"},
    )
    assert resp.status_code == 400, resp.text


async def test_use_mask_of_many_faces_empty_desc_still_succeeds(
    gm_client, gm_ws, roster,
):
    """Disguise without a description still succeeds. The broadcast
    surfaces a generic "1 hour duration" feature_desc instead of
    the specific disguise text.
    """
    magnus = roster["Magnus Hexbinder"]
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_mask_of_many_faces",
        json={"character_id": magnus["id"]},
    )
    assert resp.status_code == 200, resp.text
    msg = await gm_ws.wait_for("feature_used")
    desc = msg["data"].get("feature_desc") or ""
    assert "1 hour duration" in desc
