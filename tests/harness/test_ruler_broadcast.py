"""Ruler-broadcast fan-out endpoint — Phase 3E of the ruler/range plan.

v2.49.84 — `POST /api/campaign/{cid}/ruler_broadcast` fans out the
requester's ruler measurement to every connected client in the
campaign. Auth: any campaign member.

Server side does NO persistence — it's purely a fan-out path.
Clients render the broadcast via a ``_remoteRulers`` map; expiry +
cleanup happen on the receiving side.

Tests:
  - show action: 200 + WS ``ruler_broadcast`` with the documented
    shape (user_id, user_name, action, points, multi_segment).
  - hide action: 200 + WS broadcast with action=hide.
  - invalid action: 400.
  - non-member (no auth path here since require_user blocks; use a
    bogus campaign id instead → 403 / 404 depending on path).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def test_ruler_broadcast_show(gm_client, gm_ws):
    """POST show → WS ruler_broadcast with the requester's user_id +
    points + multi_segment flag."""
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/ruler_broadcast",
        json={
            "action": "show",
            "points": [
                {"x": 100, "y": 100},
                {"x": 240, "y": 100},
            ],
            "multi_segment": False,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True}

    msg = await gm_ws.wait_for("ruler_broadcast", timeout=2.0)
    d = msg["data"]
    assert d["action"] == "show"
    assert isinstance(d["user_id"], int) and d["user_id"] > 0
    assert isinstance(d["user_name"], str) and d["user_name"]
    assert d["points"] == [{"x": 100.0, "y": 100.0}, {"x": 240.0, "y": 100.0}]
    assert d["multi_segment"] is False


async def test_ruler_broadcast_show_multi_segment(gm_client, gm_ws):
    """Multi-segment: points array carries 3+ entries + multi_segment=true."""
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/ruler_broadcast",
        json={
            "action": "show",
            "points": [
                {"x": 100, "y": 100},
                {"x": 240, "y": 100},
                {"x": 240, "y": 240},
                {"x": 380, "y": 240},
            ],
            "multi_segment": True,
        },
    )
    assert r.status_code == 200, r.text
    msg = await gm_ws.wait_for("ruler_broadcast", timeout=2.0)
    d = msg["data"]
    assert d["multi_segment"] is True
    assert len(d["points"]) == 4


async def test_ruler_broadcast_hide(gm_client, gm_ws):
    """POST hide → WS broadcast with action=hide and no points field
    required."""
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/ruler_broadcast",
        json={"action": "hide"},
    )
    assert r.status_code == 200, r.text
    msg = await gm_ws.wait_for("ruler_broadcast", timeout=2.0)
    d = msg["data"]
    assert d["action"] == "hide"
    assert isinstance(d["user_id"], int) and d["user_id"] > 0
    # hide doesn't carry points / multi_segment.
    assert "points" not in d
    assert "multi_segment" not in d


async def test_ruler_broadcast_invalid_action(gm_client):
    """Action other than show / hide → 400."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/ruler_broadcast",
        json={"action": "explode"},
    )
    assert r.status_code == 400, r.text


async def test_ruler_broadcast_invalid_points_type(gm_client):
    """Non-list points → 400."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/ruler_broadcast",
        json={"action": "show", "points": "not a list"},
    )
    assert r.status_code == 400, r.text


async def test_ruler_broadcast_non_member_403(gm_client):
    """Non-existent campaign → 403 (membership check fails)."""
    r = await gm_client.post(
        "/api/campaign/99999/ruler_broadcast",
        json={"action": "hide"},
    )
    assert r.status_code == 403, r.text
