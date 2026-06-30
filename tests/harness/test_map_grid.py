"""v2.769.0 — map grid size + offset endpoint.

`POST /campaign/{cid}/settings/maps/{map_id}/grid_size` sets `grid_size_px`
and (new) optional `grid_offset_x` / `grid_offset_y`, clamped to [0, size).
GM-only.
"""
from .conftest import CAMPAIGN_ID


async def _active_map_id(gm_client) -> int:
    return int((await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/active-map")).json()["map_id"])


async def test_grid_size_and_offsets(gm_client):
    mid = await _active_map_id(gm_client)
    try:
        r = await gm_client.post(
            f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/grid_size",
            json={"grid_size_px": 60, "grid_offset_x": 15, "grid_offset_y": 5})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["grid_size_px"] == 60
        assert body["grid_offset_x"] == 15 and body["grid_offset_y"] == 5

        # Offset clamps to < grid size.
        r2 = await gm_client.post(
            f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/grid_size",
            json={"grid_size_px": 60, "grid_offset_x": 999})
        assert r2.json()["grid_offset_x"] == 59  # clamped to size-1
    finally:
        await gm_client.post(
            f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/grid_size",
            json={"grid_size_px": 70, "grid_offset_x": 0, "grid_offset_y": 0})


async def test_grid_size_requires_gm(gm_client, alice_client):
    mid = await _active_map_id(gm_client)
    r = await alice_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/grid_size",
        json={"grid_size_px": 50})
    assert r.status_code == 403, r.text
