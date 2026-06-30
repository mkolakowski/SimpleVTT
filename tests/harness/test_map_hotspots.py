"""v2.756.0 — Maps 2.0 clickable hotspots.

  - `GET  /api/campaign/{cid}/map/{map_id}/hotspots`  — read markers.
  - `PUT  /api/campaign/{cid}/map/{map_id}/hotspots`  — replace (GM-only) +
    broadcast `hotspots_update`.
  - `GET  /api/campaign/{cid}/active-map`             — surfaces hotspots too.

Hotspots are `{id, x, y, label, description}` markers in map-pixel coords.
"""
from .conftest import CAMPAIGN_ID


async def _active_map_id(gm_client) -> int:
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/active-map")
    assert r.status_code == 200, r.text
    mid = r.json().get("map_id")
    assert mid, "demo campaign should have an active map"
    return int(mid)


async def test_set_and_get_hotspots(gm_client, gm_ws):
    mid = await _active_map_id(gm_client)
    spots = [
        {"x": 100, "y": 150, "label": "Altar", "description": "A bloodied altar."},
        {"id": "h2", "x": 400, "y": 220, "label": "Lever"},
        {"y": 5},  # dropped — no x
    ]
    try:
        r = await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/hotspots",
            json={"hotspots": spots})
        assert r.status_code == 200, r.text
        hs = r.json()["hotspots"]
        assert len(hs) == 2, hs
        assert hs[0]["label"] == "Altar" and hs[0]["x"] == 100.0
        assert hs[0]["id"]  # auto-id filled

        msg = await gm_ws.wait_for("hotspots_update")
        assert msg["data"]["map_id"] == mid
        assert len(msg["data"]["hotspots"]) == 2

        got = await gm_client.get(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/hotspots")
        assert len(got.json()["hotspots"]) == 2
        am = (await gm_client.get(
            f"/api/campaign/{CAMPAIGN_ID}/active-map")).json()
        assert len(am["hotspots"]) == 2
    finally:
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/hotspots",
            json={"hotspots": []})


async def test_set_hotspots_requires_gm(gm_client, alice_client):
    mid = await _active_map_id(gm_client)
    assert (await alice_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/hotspots")).status_code == 200
    r = await alice_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/hotspots",
        json={"hotspots": [{"x": 1, "y": 1, "label": "x"}]})
    assert r.status_code == 403, r.text


async def test_hotspots_unknown_map_404(gm_client):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/map/99999999/hotspots")
    assert r.status_code == 404, r.text
