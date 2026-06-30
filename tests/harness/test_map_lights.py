"""v2.765.0 — Maps 2.0 placeable light sources.

  - `GET  /api/campaign/{cid}/map/{map_id}/lights`  — read lights (any member).
  - `PUT  /api/campaign/{cid}/map/{map_id}/lights`  — replace (GM-only) +
    broadcast `lights_update`.
  - `GET  /api/campaign/{cid}/active-map`           — surfaces lights too.

Lights are `{id, x, y, bright_ft, dim_ft, color}` in map-pixel coords; the
tabletop lighting overlay punches a bright/dim hole at each.
"""
from .conftest import CAMPAIGN_ID


async def _active_map_id(gm_client) -> int:
    return int((await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/active-map")).json()["map_id"])


async def test_set_and_get_lights(gm_client, gm_ws):
    mid = await _active_map_id(gm_client)
    lights = [
        {"x": 100, "y": 120, "bright_ft": 20, "dim_ft": 40, "color": "#ffd27f"},
        {"y": 5},  # dropped — no x
    ]
    try:
        r = await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights",
            json={"lights": lights})
        assert r.status_code == 200, r.text
        ls = r.json()["lights"]
        assert len(ls) == 1, ls
        assert ls[0]["bright_ft"] == 20.0 and ls[0]["dim_ft"] == 40.0
        assert ls[0]["id"]

        msg = await gm_ws.wait_for("lights_update")
        assert msg["data"]["map_id"] == mid
        assert len(msg["data"]["lights"]) == 1

        got = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights")
        assert len(got.json()["lights"]) == 1
        am = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/active-map")).json()
        assert len(am["lights"]) == 1
    finally:
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights", json={"lights": []})


async def test_negative_radius_clamped(gm_client):
    mid = await _active_map_id(gm_client)
    try:
        r = await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights",
            json={"lights": [{"x": 1, "y": 1, "bright_ft": -5, "dim_ft": "x"}]})
        L = r.json()["lights"][0]
        assert L["bright_ft"] == 0.0 and L["dim_ft"] == 0.0
    finally:
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights", json={"lights": []})


async def test_light_type_round_trips(gm_client):
    # v2.778.0 — the optional light-source preset tag persists.
    mid = await _active_map_id(gm_client)
    try:
        r = await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights",
            json={"lights": [
                {"x": 10, "y": 10, "bright_ft": 60, "dim_ft": 60,
                 "color": "#ffffff", "type": "daylight"},
                {"x": 20, "y": 20, "bright_ft": 20, "dim_ft": 20},  # no type
            ]})
        ls = r.json()["lights"]
        assert ls[0]["type"] == "daylight", ls
        assert ls[1]["type"] == "", ls  # absent → empty string
    finally:
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights", json={"lights": []})


async def test_set_lights_requires_gm(gm_client, alice_client):
    mid = await _active_map_id(gm_client)
    assert (await alice_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights")).status_code == 200
    r = await alice_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights",
        json={"lights": [{"x": 1, "y": 1, "bright_ft": 10}]})
    assert r.status_code == 403, r.text


async def test_lights_unknown_map_404(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/map/99999999/lights")
    assert r.status_code == 404, r.text
