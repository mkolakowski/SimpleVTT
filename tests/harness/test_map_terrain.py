"""v2.789.0 — Maps 2.0 terrain regions.

  - `GET  /api/campaign/{cid}/map/{map_id}/terrain`  — read (any member).
  - `PUT  /api/campaign/{cid}/map/{map_id}/terrain`  — replace (GM-only) +
    broadcast `terrain_update`.
  - `GET  /api/campaign/{cid}/active-map`            — surfaces terrain too.

Terrain regions are `{id, x, y, w, h, type}` rectangles in map-pixel coords.
v2.848.0 — a region may also carry `points` (exactly 4 numeric [x, y] corner
pairs) making it a free-form quad; the server recomputes x/y/w/h as its bbox.
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


async def test_terrain_quad_points_round_trip(gm_client, gm_ws):
    """v2.848.0 — a 4-point free-form quad persists through PUT/GET + the
    broadcast, with x/y/w/h recomputed as its bounding box; malformed `points`
    (wrong count / non-numeric) are dropped while the record's rect survives
    (or the record is dropped when it has no valid rect either)."""
    mid = await _active_map_id(gm_client)
    regions = [
        # A valid quad — bbox should be x=100, y=50, w=300, h=250.
        {"id": "quad1", "type": "swamp",
         "points": [[120, 50], [400, 90], [350, 300], [100, 260]]},
        # v2.855.0 — a single point is invalid `points`; falls back to its rect.
        {"id": "one", "x": 10, "y": 10, "w": 60, "h": 60,
         "points": [[0, 0]]},
        # Non-numeric vertex → dropped entirely (no valid rect either).
        {"id": "junk", "points": [["a", "b"], [1, 2], [3, 4], [5, 6]]},
    ]
    try:
        r = await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/terrain",
            json={"terrain": regions})
        assert r.status_code == 200, r.text
        ts = r.json()["terrain"]
        assert len(ts) == 2, ts
        quad = next(t for t in ts if t["id"] == "quad1")
        assert quad["points"] == [[120.0, 50.0], [400.0, 90.0],
                                  [350.0, 300.0], [100.0, 260.0]]
        assert (quad["x"], quad["y"], quad["w"], quad["h"]) == (100.0, 50.0, 300.0, 250.0)
        assert quad["type"] == "swamp"
        one = next(t for t in ts if t["id"] == "one")
        assert "points" not in one and one["w"] == 60.0   # rect fallback

        msg = await gm_ws.wait_for("terrain_update")
        bquad = next(t for t in msg["data"]["terrain"] if t["id"] == "quad1")
        assert len(bquad["points"]) == 4

        got = (await gm_client.get(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/terrain")).json()
        gquad = next(t for t in got["terrain"] if t["id"] == "quad1")
        assert gquad["points"] == quad["points"]
    finally:
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/terrain", json={"terrain": []})


async def test_terrain_polygon_points_round_trip(gm_client):
    """v2.855.0 — free-polygon terrain: 3..N vertices round-trip with the bbox
    recomputed; a 2-point `points` is invalid → the record falls back to its
    rect (or drops if it has none)."""
    mid = await _active_map_id(gm_client)
    regions = [
        # A triangle — bbox x=10,y=0,w=90,h=80.
        {"id": "tri", "type": "lava",
         "points": [[10, 0], [100, 40], [55, 80]]},
        # A 6-gon.
        {"id": "hex", "type": "water",
         "points": [[200, 100], [260, 110], [290, 160],
                    [260, 210], [200, 200], [175, 155]]},
        # Only 2 points → invalid; falls back to its rect fields.
        {"id": "seg", "x": 5, "y": 5, "w": 40, "h": 40,
         "points": [[0, 0], [10, 10]]},
    ]
    try:
        r = await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/terrain",
            json={"terrain": regions})
        assert r.status_code == 200, r.text
        ts = {t["id"]: t for t in r.json()["terrain"]}
        assert len(ts["tri"]["points"]) == 3
        assert (ts["tri"]["x"], ts["tri"]["y"], ts["tri"]["w"], ts["tri"]["h"]) == (10.0, 0.0, 90.0, 80.0)
        assert len(ts["hex"]["points"]) == 6 and ts["hex"]["type"] == "water"
        assert "points" not in ts["seg"] and ts["seg"]["w"] == 40.0  # rect fallback
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
