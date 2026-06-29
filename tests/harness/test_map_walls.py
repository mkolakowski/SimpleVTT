"""v2.752.0 — Maps 2.0 walls & doors storage substrate.

  - `GET  /api/campaign/{cid}/active-map`            — active map id + walls.
  - `GET  /api/campaign/{cid}/map/{map_id}/walls`    — read wall segments.
  - `PUT  /api/campaign/{cid}/map/{map_id}/walls`    — replace (GM-only) +
    broadcast `walls_update`.

Walls are stored as a JSON list of `{id, x1, y1, x2, y2, door, open}` line
segments on the map; doors are segments with `door: true`.
"""
from .conftest import CAMPAIGN_ID


async def _active_map_id(gm_client) -> int:
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/active-map")
    assert r.status_code == 200, r.text
    mid = r.json().get("map_id")
    assert mid, "demo campaign should have an active map"
    return int(mid)


async def test_set_and_get_walls_with_broadcast(gm_client, gm_ws):
    mid = await _active_map_id(gm_client)
    segs = [
        {"x1": 10, "y1": 20, "x2": 110, "y2": 20},  # a wall (id auto-filled)
        {"id": "door1", "x1": 110, "y1": 20, "x2": 110, "y2": 120,
         "door": True, "open": False},               # a closed door
        {"x1": "bad"},                                # dropped (no coords)
    ]
    try:
        r = await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls",
            json={"walls": segs})
        assert r.status_code == 200, r.text
        walls = r.json()["walls"]
        assert len(walls) == 2, walls           # the bad segment dropped
        assert walls[0]["id"]                    # auto-id filled
        assert walls[0]["x1"] == 10.0 and walls[0]["door"] is False
        door = next(w for w in walls if w["id"] == "door1")
        assert door["door"] is True and door["open"] is False

        # WS broadcast carries the new wall list for the map.
        msg = await gm_ws.wait_for("walls_update")
        assert msg["data"]["map_id"] == mid
        assert len(msg["data"]["walls"]) == 2

        # GET round-trips the persisted walls.
        got = await gm_client.get(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls")
        assert got.status_code == 200
        assert len(got.json()["walls"]) == 2
        # active-map also surfaces them.
        am = (await gm_client.get(
            f"/api/campaign/{CAMPAIGN_ID}/active-map")).json()
        assert len(am["walls"]) == 2
    finally:
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})


async def test_set_walls_requires_gm(gm_client, alice_client):
    mid = await _active_map_id(gm_client)
    # A non-GM member can read walls but not write them.
    assert (await alice_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls")).status_code == 200
    r = await alice_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls",
        json={"walls": [{"x1": 0, "y1": 0, "x2": 1, "y2": 1}]})
    assert r.status_code == 403, r.text


async def test_walls_unknown_map_404(gm_client):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/map/99999999/walls")
    assert r.status_code == 404, r.text
