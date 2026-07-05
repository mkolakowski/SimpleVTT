"""v2.915.0 — per-token size override via PATCH /token/{id}.

The GM sets an individual token's size (1..4 grid cells) from the tabletop
Players/Tokens drawer (edit mode). Size combines with the per-map token_scale.

  - `PATCH /api/campaign/{cid}/token/{id}` with `{size}` — GM-only, clamps to
    [1, 4], broadcasts `token_update` carrying the new size.
"""
from .conftest import CAMPAIGN_ID


async def _place_mira(gm_client, roster):
    mira = roster["Mira Greenleaf"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/place-token",
        json={"x": 300.0, "y": 300.0})
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")
    for t in r.json()["tokens"]:
        if t.get("character_id") == mira["id"]:
            return t
    raise AssertionError("Mira's token not found")


async def test_set_token_size_round_trips(gm_client, gm_ws, roster):
    tok = await _place_mira(gm_client, roster)
    try:
        r = await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/token/{tok['id']}", json={"size": 3})
        assert r.status_code == 200, r.text
        assert r.json()["size"] == 3

        msg = await gm_ws.wait_for("token_update")
        assert msg["data"]["id"] == tok["id"]
        assert msg["data"]["size"] == 3
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/token/{tok['id']}", json={"size": 1})


async def test_token_size_clamps_out_of_range(gm_client, roster):
    tok = await _place_mira(gm_client, roster)
    try:
        r = await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/token/{tok['id']}", json={"size": 99})
        assert r.json()["size"] == 4, r.text  # clamped to Gargantuan
        r = await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/token/{tok['id']}", json={"size": 0})
        assert r.json()["size"] == 1, r.text  # clamped to Medium
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/token/{tok['id']}", json={"size": 1})


async def test_bad_token_size_400(gm_client, roster):
    tok = await _place_mira(gm_client, roster)
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/token/{tok['id']}", json={"size": "huge"})
    assert r.status_code == 400, r.text


async def test_set_token_size_requires_gm(gm_client, alice_client, roster):
    tok = await _place_mira(gm_client, roster)
    try:
        r = await alice_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/token/{tok['id']}", json={"size": 2})
        assert r.status_code == 403, r.text
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/token/{tok['id']}", json={"size": 1})
