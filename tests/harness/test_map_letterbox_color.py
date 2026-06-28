"""/campaign/{cid}/settings/maps/{mid}/letterbox_color — average-colour surround toggle.

Covers the v2.733.0 GM toggle that paints the canvas surround (letterbox
gutter + #map-pane) the map image's average colour:
  - happy path: enable → 200 + #rrggbb colour + map_letterbox_color WS broadcast;
    disable → 200 + null colour + broadcast.
  - error path: 404 on an unknown map id; 403 for a non-GM player.
"""
import re

from .conftest import CAMPAIGN_ID

_HEX = re.compile(r"^#[0-9a-f]{6}$")


async def _active_map_id(client) -> int:
    r = await client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")
    assert r.status_code == 200, r.text
    return r.json()["map_id"]


async def test_letterbox_enable_then_disable(gm_client, gm_ws):
    map_id = await _active_map_id(gm_client)
    base = f"/campaign/{CAMPAIGN_ID}/settings/maps/{map_id}/letterbox_color"

    # Enable → computes the map image's average colour, stores + broadcasts it.
    gm_ws.mark()
    resp = await gm_client.post(base, json={"enabled": True})
    assert resp.status_code == 200, resp.text
    color = resp.json()["letterbox_color"]
    assert color and _HEX.match(color), color

    msg = await gm_ws.wait_for("map_letterbox_color")
    assert msg["data"]["map_id"] == map_id
    assert msg["data"]["letterbox_color"] == color

    # Disable → cleared back to null + broadcast. mark() so wait_for sees the
    # disable broadcast, not the (non-consumed) enable one above.
    gm_ws.mark()
    resp = await gm_client.post(base, json={"enabled": False})
    assert resp.status_code == 200, resp.text
    assert resp.json()["letterbox_color"] is None

    msg = await gm_ws.wait_for("map_letterbox_color")
    assert msg["data"]["map_id"] == map_id
    assert msg["data"]["letterbox_color"] is None


async def test_letterbox_unknown_map_404(gm_client):
    resp = await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings/maps/99999999/letterbox_color",
        json={"enabled": True},
    )
    assert resp.status_code == 404, resp.text


async def test_letterbox_player_forbidden(gm_client, alice_client):
    map_id = await _active_map_id(gm_client)
    resp = await alice_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings/maps/{map_id}/letterbox_color",
        json={"enabled": True},
    )
    assert resp.status_code == 403, resp.text
