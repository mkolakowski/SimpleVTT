"""v2.790.0 — GM-only map pins.

  - `GET /api/campaign/{cid}/map/{id}/gm_pins`  — GM-only (never to players).
  - `PUT /api/campaign/{cid}/map/{id}/gm_pins`  — GM-only + data-less
    `gm_pins_changed` broadcast.
"""
from .conftest import CAMPAIGN_ID


async def _active_map_id(gm_client) -> int:
    return int((await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/active-map")).json()["map_id"])


async def test_set_and_get_gm_pins(gm_client, gm_ws):
    mid = await _active_map_id(gm_client)
    try:
        r = await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/gm_pins",
            json={"gm_pins": [{"x": 300, "y": 220, "label": "Trap",
                               "note": "DC 15 Dex, 3d6 fire"}]})
        assert r.status_code == 200, r.text
        ps = r.json()["gm_pins"]
        assert len(ps) == 1 and ps[0]["label"] == "Trap" and ps[0]["id"]

        # The broadcast carries NO pin data (players must never see it).
        msg = await gm_ws.wait_for("gm_pins_changed")
        assert msg["data"]["map_id"] == mid
        assert "gm_pins" not in msg["data"] and "note" not in str(msg["data"])

        got = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/gm_pins")
        assert got.json()["gm_pins"][0]["note"] == "DC 15 Dex, 3d6 fire"
        # GM pins are NOT surfaced on the shared active-map payload.
        am = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/active-map")).json()
        assert "gm_pins" not in am
    finally:
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/gm_pins", json={"gm_pins": []})


async def test_gm_pins_hidden_from_players(gm_client, alice_client):
    mid = await _active_map_id(gm_client)
    # A non-GM member can neither read nor write GM pins.
    assert (await alice_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/gm_pins")).status_code == 403
    r = await alice_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/gm_pins",
        json={"gm_pins": [{"x": 1, "y": 1}]})
    assert r.status_code == 403, r.text


async def test_gm_pins_unknown_map_404(gm_client):
    assert (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/map/99999999/gm_pins")).status_code == 404
