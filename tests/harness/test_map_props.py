"""v2.791.0 — Maps 2.0 decorative prop stamps.

  - `GET  /api/campaign/{cid}/map/{map_id}/props`  — read (any member).
  - `PUT  /api/campaign/{cid}/map/{map_id}/props`  — replace (GM-only) +
    broadcast `props_update`.
  - `GET  /api/campaign/{cid}/active-map`          — surfaces props too.

Props are `{id, x, y, kind, size, rot}` emoji stamps in map-pixel coords;
`size` is clamped to 8..400 px, `rot` wrapped to 0..359°, `kind` defaults.
"""
from .conftest import CAMPAIGN_ID


async def _active_map_id(gm_client) -> int:
    return int((await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/active-map")).json()["map_id"])


async def test_set_and_get_props(gm_client, gm_ws):
    mid = await _active_map_id(gm_client)
    props = [
        {"x": 120, "y": 200, "kind": "🌲", "size": 900, "rot": 420},  # clamped
        {"x": 50, "y": 60},  # no kind → default glyph, default size
        {"y": 10},           # dropped — no numeric x
    ]
    try:
        r = await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/props",
            json={"props": props})
        assert r.status_code == 200, r.text
        ps = r.json()["props"]
        assert len(ps) == 2, ps
        tree = ps[0]
        assert tree["kind"] == "🌲" and tree["id"]
        assert tree["size"] == 400.0          # clamped down from 900
        assert tree["rot"] == 60.0            # 420 % 360
        assert ps[1]["kind"] == "📦"          # default glyph
        assert ps[1]["size"] == 40.0          # default size

        msg = await gm_ws.wait_for("props_update")
        assert msg["data"]["map_id"] == mid
        assert len(msg["data"]["props"]) == 2

        am = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/active-map")).json()
        assert len(am["props"]) == 2
    finally:
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/props", json={"props": []})


async def test_set_props_requires_gm(gm_client, alice_client):
    mid = await _active_map_id(gm_client)
    # A player can read props (needs them to render the scene)...
    assert (await alice_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/props")).status_code == 200
    # ...but cannot write them.
    r = await alice_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/props",
        json={"props": [{"x": 0, "y": 0, "kind": "🪑"}]})
    assert r.status_code == 403, r.text


async def test_props_unknown_map_404(gm_client):
    assert (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/map/99999999/props")).status_code == 404
