"""v2.858.0 — GM reveal/hide terrain for players.

Terrain overlays are hidden from players by default (`Map.terrain_hidden`
true); a GM toggle reveals them. `POST …/settings/maps/{mid}/terrain_visibility`
(GM-only) flips the flag + broadcasts `terrain_visibility_update`; the flag is
surfaced on `/active-map`.
"""
from .conftest import CAMPAIGN_ID


async def _active_map_id(gm_client) -> int:
    return int((await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/active-map")).json()["map_id"])


async def test_terrain_visibility_round_trips(gm_client, gm_ws):
    mid = await _active_map_id(gm_client)
    try:
        # Reveal to players.
        r = await gm_client.post(
            f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/terrain_visibility",
            json={"hidden": False})
        assert r.status_code == 200, r.text
        assert r.json()["terrain_hidden"] is False

        msg = await gm_ws.wait_for("terrain_visibility_update")
        assert msg["data"]["map_id"] == mid
        assert msg["data"]["terrain_hidden"] is False

        am = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/active-map")).json()
        assert am["terrain_hidden"] is False

        # Hide again.
        r2 = await gm_client.post(
            f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/terrain_visibility",
            json={"hidden": True})
        assert r2.json()["terrain_hidden"] is True
    finally:
        await gm_client.post(
            f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/terrain_visibility",
            json={"hidden": True})


async def test_terrain_visibility_requires_gm(gm_client, alice_client):
    mid = await _active_map_id(gm_client)
    r = await alice_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/terrain_visibility",
        json={"hidden": False})
    assert r.status_code == 403, r.text


async def test_terrain_visibility_unknown_map_404(gm_client):
    r = await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings/maps/99999999/terrain_visibility",
        json={"hidden": False})
    assert r.status_code == 404, r.text
