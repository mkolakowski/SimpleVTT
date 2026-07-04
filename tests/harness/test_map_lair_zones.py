"""v2.869.0 — lair-action zones (Phase 1: storage + endpoints).

A lair zone is a labelled area (like a terrain region, but carrying a list of
associated lair-action ids) that marks where a creature's lair actions strike.
It is placed in the map editor and used on the tabletop as a toggleable overlay
+ to drive AoE targeting when a lair action fires.

  - `GET  /api/campaign/{cid}/map/{map_id}/lair_zones`  — read (any member).
  - `PUT  /api/campaign/{cid}/map/{map_id}/lair_zones`  — replace (GM-only) +
    broadcast `lair_zones_update`.
  - `GET  /api/campaign/{cid}/active-map`               — surfaces lair_zones.

Zone shape: `{id, x, y, w, h, points?, label, actions[]}` in map-pixel coords.
Geometry mirrors terrain (rect, or a 3..40-vertex polygon with bbox recomputed).
"""
from .conftest import CAMPAIGN_ID


async def _active_map_id(gm_client) -> int:
    return int((await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/active-map")).json()["map_id"])


async def test_set_and_get_lair_zones(gm_client, gm_ws):
    mid = await _active_map_id(gm_client)
    zones = [
        {"x": 200, "y": 220, "w": 160, "h": 90, "label": "Magma vent",
         "actions": ["magma-erupts", "tremor"], "color": "#3B8EA5",
         "bad_color": "not-a-hex"},
        {"x": 5, "y": 5, "w": 0, "h": 40, "label": "bad"},  # dropped — zero width
    ]
    try:
        r = await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lair_zones",
            json={"lair_zones": zones})
        assert r.status_code == 200, r.text
        lz = r.json()["lair_zones"]
        assert len(lz) == 1, lz
        assert lz[0]["label"] == "Magma vent"
        assert lz[0]["actions"] == ["magma-erupts", "tremor"]
        assert lz[0]["w"] == 160.0 and lz[0]["id"]
        # v2.877.0 — a valid #rrggbb colour round-trips (lowercased); the bad
        # one is dropped, and a stray field never leaks through.
        assert lz[0]["color"] == "#3b8ea5"
        assert "bad_color" not in lz[0]

        msg = await gm_ws.wait_for("lair_zones_update")
        assert msg["data"]["map_id"] == mid
        assert len(msg["data"]["lair_zones"]) == 1

        # Any-member GET + the /active-map bootstrap both surface it.
        got = (await gm_client.get(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lair_zones")).json()
        assert len(got["lair_zones"]) == 1
        am = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/active-map")).json()
        assert len(am["lair_zones"]) == 1
    finally:
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lair_zones",
            json={"lair_zones": []})


async def test_lair_zone_polygon_round_trip(gm_client):
    """A 4-vertex polygon persists with x/y/w/h recomputed as its bbox; a
    2-point set is invalid and falls back to the rect fields."""
    mid = await _active_map_id(gm_client)
    try:
        r = await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lair_zones",
            json={"lair_zones": [
                {"points": [[100, 100], [300, 120], [280, 260], [90, 240]],
                 "label": "Cavern floor", "actions": ["cave-in"]},
                {"points": [[0, 0], [10, 10]], "x": 400, "y": 400, "w": 60, "h": 60,
                 "label": "fallback"},
            ]})
        lz = r.json()["lair_zones"]
        assert len(lz) == 2, lz
        poly = lz[0]
        assert len(poly["points"]) == 4
        assert poly["x"] == 90.0 and poly["y"] == 100.0        # bbox min
        assert poly["w"] == 210.0 and poly["h"] == 160.0        # bbox span
        # The 2-point (invalid polygon) record fell back to its rect fields.
        assert "points" not in lz[1] and lz[1]["w"] == 60.0
    finally:
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lair_zones",
            json={"lair_zones": []})


async def test_set_lair_zones_requires_gm(gm_client, alice_client):
    """A non-GM member can read but not write lair zones."""
    mid = await _active_map_id(gm_client)
    # Read is allowed for any member.
    rg = await alice_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lair_zones")
    assert rg.status_code == 200, rg.text
    # Write is GM-only → 403.
    rw = await alice_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lair_zones",
        json={"lair_zones": [{"x": 0, "y": 0, "w": 40, "h": 40}]})
    assert rw.status_code == 403, rw.text


async def test_set_lair_zones_unknown_map_404(gm_client):
    r = await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/map/99999/lair_zones",
        json={"lair_zones": []})
    assert r.status_code == 404, r.text
