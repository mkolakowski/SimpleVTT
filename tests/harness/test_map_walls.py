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


async def test_gate_flip_opacity_round_trip(gm_client):
    # v2.787.0 — gate / flip / opacity persist; opacity clamps to [0,1].
    mid = await _active_map_id(gm_client)
    try:
        r = await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": [
                {"x1": 0, "y1": 0, "x2": 70, "y2": 0, "gate": True, "flip": True,
                 "open": False, "opacity": 0.4},
                {"x1": 0, "y1": 5, "x2": 70, "y2": 5, "opacity": 5},   # clamps to 1
                {"x1": 0, "y1": 9, "x2": 70, "y2": 9},                 # defaults
            ]})
        ws = r.json()["walls"]
        assert ws[0]["gate"] is True and ws[0]["flip"] is True and ws[0]["opacity"] == 0.4, ws[0]
        assert ws[1]["opacity"] == 1.0, ws[1]
        assert ws[2]["gate"] is False and ws[2]["opacity"] == 1.0, ws[2]
    finally:
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})


async def test_window_secret_round_trip(gm_client):
    # v2.788.2 — window + secret flags persist through PUT/GET.
    mid = await _active_map_id(gm_client)
    try:
        r = await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": [
                {"id": "win", "x1": 50, "y1": 0, "x2": 50, "y2": 100, "window": True},
                {"id": "sd", "x1": 80, "y1": 0, "x2": 80, "y2": 100, "door": True, "secret": True},
            ]})
        ws = r.json()["walls"]
        assert ws[0]["window"] is True and ws[0]["secret"] is False, ws[0]
        assert ws[1]["secret"] is True and ws[1]["window"] is False, ws[1]
    finally:
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})


async def test_gate_toggle_opens(gm_client):
    # v2.787.0 — a gate toggles open/closed via the door-toggle endpoint.
    mid = await _active_map_id(gm_client)
    try:
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": [
                {"id": "g1", "x1": 0, "y1": 0, "x2": 70, "y2": 0, "gate": True, "open": False}]})
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/door/g1/toggle")
        assert r.status_code == 200, r.text
        assert r.json()["open"] is True
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
