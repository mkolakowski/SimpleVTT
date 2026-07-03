"""v2.766.0 — Maps 2.0 fog of war.

  - `GET  /api/campaign/{cid}/map/{map_id}/fog`  — read fog state (any member).
  - `PUT  /api/campaign/{cid}/map/{map_id}/fog`  — set enabled + revealed rects
    (GM-only) + broadcast `fog_update`.
  - `GET  /api/campaign/{cid}/active-map`        — surfaces fog too.

Revealed rects are `{x, y, w, h}` in map-pixel coords; zero/negative-size
rects are dropped.
"""
from .conftest import CAMPAIGN_ID


async def _active_map_id(gm_client) -> int:
    return int((await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/active-map")).json()["map_id"])


async def test_set_and_get_fog(gm_client, gm_ws):
    mid = await _active_map_id(gm_client)
    try:
        r = await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/fog",
            json={"enabled": True, "revealed": [
                {"x": 10, "y": 20, "w": 200, "h": 150},
                {"x": 0, "y": 0, "w": 0, "h": 0},  # dropped — zero size
            ]})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["fog_enabled"] is True
        assert len(body["fog_revealed"]) == 1
        assert body["fog_revealed"][0]["w"] == 200.0

        msg = await gm_ws.wait_for("fog_update")
        assert msg["data"]["map_id"] == mid
        assert msg["data"]["fog_enabled"] is True

        am = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/active-map")).json()
        assert am["fog_enabled"] is True and len(am["fog_revealed"]) == 1
    finally:
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/fog",
            json={"enabled": False, "revealed": []})


async def test_fog_enabled_only_patch(gm_client):
    """Sending only `enabled` leaves the revealed rects untouched, and vice
    versa."""
    mid = await _active_map_id(gm_client)
    try:
        await gm_client.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/fog",
                            json={"enabled": True, "revealed": [
                                {"x": 5, "y": 5, "w": 50, "h": 50}]})
        # Patch only `enabled` → revealed survives.
        r = await gm_client.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/fog",
                                json={"enabled": False})
        assert r.json()["fog_enabled"] is False
        assert len(r.json()["fog_revealed"]) == 1
    finally:
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/fog",
            json={"enabled": False, "revealed": []})


async def test_fog_dynamic_flag_round_trips(gm_client, gm_ws):
    """v2.843.0 — the `dynamic` flag (exploration mode) persists through
    PUT/GET and rides the `fog_update` broadcast."""
    mid = await _active_map_id(gm_client)
    try:
        r = await gm_client.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/fog",
                                json={"enabled": True, "dynamic": True})
        assert r.status_code == 200, r.text
        assert r.json()["fog_dynamic"] is True
        # fog_explored is always surfaced (empty by default).
        assert r.json()["fog_explored"] == []

        msg = await gm_ws.wait_for("fog_update")
        assert msg["data"]["fog_dynamic"] is True
        assert "fog_explored" in msg["data"]

        got = (await gm_client.get(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/fog")).json()
        assert got["fog_dynamic"] is True
        am = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/active-map")).json()
        assert am["fog_dynamic"] is True
    finally:
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/fog",
            json={"enabled": False, "dynamic": False, "revealed": []})


async def test_set_fog_requires_gm(gm_client, alice_client):
    mid = await _active_map_id(gm_client)
    assert (await alice_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/fog")).status_code == 200
    r = await alice_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/fog", json={"enabled": True})
    assert r.status_code == 403, r.text


async def test_fog_unknown_map_404(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/map/99999999/fog")
    assert r.status_code == 404, r.text
