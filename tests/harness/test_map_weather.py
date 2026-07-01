"""v2.807.0 — per-map ambient weather overlay setter.

  - `POST /campaign/{cid}/settings/maps/{map_id}/weather` — set (GM-only) +
    broadcast `weather_update`.
  - `GET  /api/campaign/{cid}/active-map`                 — surfaces weather.
"""
from .conftest import CAMPAIGN_ID


async def _mid(gm_client):
    return int((await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/active-map")).json()["map_id"])


async def test_set_weather_round_trips(gm_client, gm_ws):
    mid = await _mid(gm_client)
    try:
        r = await gm_client.post(
            f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/weather",
            json={"weather": "rain"})
        assert r.status_code == 200, r.text
        assert r.json()["weather"] == "rain"

        msg = await gm_ws.wait_for("weather_update")
        assert msg["data"]["map_id"] == mid and msg["data"]["weather"] == "rain"

        am = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/active-map")).json()
        assert am["weather"] == "rain", am
    finally:
        await gm_client.post(
            f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/weather",
            json={"weather": "none"})


async def test_weather_none_clears(gm_client):
    mid = await _mid(gm_client)
    await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/weather", json={"weather": "snow"})
    r = await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/weather", json={"weather": "none"})
    assert r.json()["weather"] == ""  # "none" normalises to empty


async def test_bad_weather_400(gm_client):
    mid = await _mid(gm_client)
    r = await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/weather",
        json={"weather": "locusts"})
    assert r.status_code == 400, r.text


async def test_set_weather_requires_gm(gm_client, alice_client):
    mid = await _mid(gm_client)
    r = await alice_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/weather",
        json={"weather": "rain"})
    assert r.status_code == 403, r.text
