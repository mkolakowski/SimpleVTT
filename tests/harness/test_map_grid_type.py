"""v2.788.4 — per-map grid type (square / hex / none) setter."""
from .conftest import CAMPAIGN_ID


async def _mid(gm_client):
    return int((await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/active-map")).json()["map_id"])


async def test_set_grid_type_hex_round_trips(gm_client):
    mid = await _mid(gm_client)
    try:
        r = await gm_client.post(
            f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/grid_type",
            json={"grid_type": "hex"})
        assert r.status_code == 200, r.text
        assert r.json()["grid_type"] == "hex"
        am = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/active-map")).json()
        assert am["grid_type"] == "hex", am
    finally:
        await gm_client.post(
            f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/grid_type",
            json={"grid_type": "square"})


async def test_bad_grid_type_400(gm_client):
    mid = await _mid(gm_client)
    r = await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/grid_type",
        json={"grid_type": "triangles"})
    assert r.status_code == 400, r.text


async def test_set_grid_type_requires_gm(gm_client, alice_client):
    mid = await _mid(gm_client)
    r = await alice_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/grid_type",
        json={"grid_type": "hex"})
    assert r.status_code == 403, r.text
