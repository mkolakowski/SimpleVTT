"""v2.789.0 — Maps 2.0 terrain regions.

  - `GET  /api/campaign/{cid}/map/{map_id}/terrain`  — read (any member).
  - `PUT  /api/campaign/{cid}/map/{map_id}/terrain`  — replace (GM-only) +
    broadcast `terrain_update`.
  - `GET  /api/campaign/{cid}/active-map`            — surfaces terrain too.

Terrain regions are `{id, x, y, w, h, type}` rectangles in map-pixel coords.
"""
from .conftest import CAMPAIGN_ID


async def _active_map_id(gm_client) -> int:
    return int((await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/active-map")).json()["map_id"])


async def test_set_and_get_terrain(gm_client, gm_ws):
    mid = await _active_map_id(gm_client)
    regions = [
        {"x": 100, "y": 120, "w": 140, "h": 70, "type": "water"},
        {"x": 5, "y": 5, "w": 0, "h": 40},   # dropped — zero width
    ]
    try:
        r = await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/terrain",
            json={"terrain": regions})
        assert r.status_code == 200, r.text
        ts = r.json()["terrain"]
        assert len(ts) == 1, ts
        assert ts[0]["type"] == "water" and ts[0]["w"] == 140.0 and ts[0]["id"]

        msg = await gm_ws.wait_for("terrain_update")
        assert msg["data"]["map_id"] == mid
        assert len(msg["data"]["terrain"]) == 1

        am = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/active-map")).json()
        assert len(am["terrain"]) == 1
    finally:
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/terrain", json={"terrain": []})


async def test_terrain_type_defaults(gm_client):
    mid = await _active_map_id(gm_client)
    try:
        r = await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/terrain",
            json={"terrain": [{"x": 0, "y": 0, "w": 50, "h": 50}]})
        assert r.json()["terrain"][0]["type"] == "difficult"  # default
    finally:
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/terrain", json={"terrain": []})


async def test_set_terrain_requires_gm(gm_client, alice_client):
    mid = await _active_map_id(gm_client)
    assert (await alice_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/terrain")).status_code == 200
    r = await alice_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/terrain",
        json={"terrain": [{"x": 0, "y": 0, "w": 10, "h": 10}]})
    assert r.status_code == 403, r.text


async def test_terrain_unknown_map_404(gm_client):
    assert (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/map/99999999/terrain")).status_code == 404
