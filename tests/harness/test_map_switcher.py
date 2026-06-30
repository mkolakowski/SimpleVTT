"""v2.762.0 — multi-map tabletop quick-switcher endpoints.

  - `GET  /api/campaign/{cid}/map-group`        — the current map group (any
    member); >1 entry only when the running encounter links extra maps.
  - `POST /api/campaign/{cid}/switch-map/{id}`  — flip the active map to one in
    the group (GM-only); broadcasts `map_change` so clients reload.

The demo has a single map, so the group is just the active map; switching to a
map outside the group is rejected.
"""
from .conftest import CAMPAIGN_ID


async def test_map_group_shape(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/map-group")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "active_map_id" in body and isinstance(body["maps"], list)
    assert body["maps"], "the active map should be in the group"
    for m in body["maps"]:
        assert {"id", "name", "is_active"} <= m.keys()
    # Exactly one map is flagged active.
    assert sum(1 for m in body["maps"] if m["is_active"]) == 1


async def test_switch_to_group_map_broadcasts(gm_client, gm_ws):
    grp = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/map-group")).json()
    active = grp["active_map_id"]
    r = await gm_client.post(f"/api/campaign/{CAMPAIGN_ID}/switch-map/{active}")
    assert r.status_code == 200, r.text
    assert r.json()["active_map_id"] == active
    msg = await gm_ws.wait_for("map_change")
    assert msg["data"]["map_id"] == active


async def test_switch_to_non_group_map_400(gm_client):
    r = await gm_client.post(f"/api/campaign/{CAMPAIGN_ID}/switch-map/99999999")
    assert r.status_code == 400, r.text


async def test_switch_requires_gm(alice_client):
    grp = (await alice_client.get(f"/api/campaign/{CAMPAIGN_ID}/map-group")).json()
    active = grp["active_map_id"]
    r = await alice_client.post(f"/api/campaign/{CAMPAIGN_ID}/switch-map/{active}")
    assert r.status_code == 403, r.text
