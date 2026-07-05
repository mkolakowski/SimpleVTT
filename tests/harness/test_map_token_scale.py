"""v2.913.0 — per-map default token-size multiplier.

  - `POST /campaign/{cid}/settings/maps/{map_id}/token_scale` — set (GM-only) +
    broadcast `token_scale_update`.
  - `GET  /api/campaign/{cid}/active-map`                     — surfaces token_scale.
"""
from .conftest import CAMPAIGN_ID


async def _mid(gm_client):
    return int((await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/active-map")).json()["map_id"])


async def test_set_token_scale_round_trips(gm_client, gm_ws):
    mid = await _mid(gm_client)
    try:
        r = await gm_client.post(
            f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/token_scale",
            json={"token_scale": 1.5})
        assert r.status_code == 200, r.text
        assert r.json()["token_scale"] == 1.5

        msg = await gm_ws.wait_for("token_scale_update")
        assert msg["data"]["map_id"] == mid
        assert msg["data"]["token_scale"] == 1.5

        am = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/active-map")).json()
        assert am["token_scale"] == 1.5, am
    finally:
        await gm_client.post(
            f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/token_scale",
            json={"token_scale": 1.0})


async def test_token_scale_clamps_out_of_range(gm_client):
    mid = await _mid(gm_client)
    try:
        # Above the ceiling clamps to 3.0.
        r = await gm_client.post(
            f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/token_scale",
            json={"token_scale": 99})
        assert r.json()["token_scale"] == 3.0, r.text
        # Below the floor clamps to 0.5.
        r = await gm_client.post(
            f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/token_scale",
            json={"token_scale": 0.01})
        assert r.json()["token_scale"] == 0.5, r.text
    finally:
        await gm_client.post(
            f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/token_scale",
            json={"token_scale": 1.0})


async def test_bad_token_scale_400(gm_client):
    mid = await _mid(gm_client)
    r = await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/token_scale",
        json={"token_scale": "huge"})
    assert r.status_code == 400, r.text


async def test_set_token_scale_requires_gm(gm_client, alice_client):
    mid = await _mid(gm_client)
    r = await alice_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/token_scale",
        json={"token_scale": 2.0})
    assert r.status_code == 403, r.text
