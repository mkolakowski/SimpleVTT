"""v2.843.0 — exploration-tracking fog of war (engine).

  - `POST /api/campaign/{cid}/map/{map_id}/fog/explore` — union newly-seen grid
    cells into the map's accumulated `fog_explored` memory (any member, add-only)
    + broadcast `fog_update`.
  - `POST /api/campaign/{cid}/map/{map_id}/fog/reset`   — clear `fog_explored`
    (GM-only) + broadcast `fog_update`.

Explored cells are `[col, row]` non-negative integer grid coords; the stored set
only grows via /explore (monotonic) and is wiped by /reset.
"""
from .conftest import CAMPAIGN_ID


async def _active_map_id(gm_client) -> int:
    return int((await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/active-map")).json()["map_id"])


async def _reset(gm_client, mid):
    await gm_client.post(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/fog/reset")


async def test_explore_unions_monotonically(gm_client, gm_ws):
    mid = await _active_map_id(gm_client)
    try:
        # First reveal.
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/fog/explore",
            json={"cells": [[1, 1], [1, 2], [2, 1], ["bad", 0], [3]]})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["added"] == 3            # malformed entries dropped
        assert sorted(body["fog_explored"]) == [[1, 1], [1, 2], [2, 1]]

        msg = await gm_ws.wait_for("fog_update")
        assert msg["data"]["map_id"] == mid
        assert sorted(msg["data"]["fog_explored"]) == [[1, 1], [1, 2], [2, 1]]

        # Second reveal unions (one overlap, one new) → only the new cell adds.
        r2 = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/fog/explore",
            json={"cells": [[2, 1], [9, 9]]})
        assert r2.json()["added"] == 1
        assert sorted(r2.json()["fog_explored"]) == [[1, 1], [1, 2], [2, 1], [9, 9]]
    finally:
        await _reset(gm_client, mid)


async def test_explore_repeat_is_noop(gm_client):
    mid = await _active_map_id(gm_client)
    try:
        await gm_client.post(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/fog/explore",
                             json={"cells": [[4, 4]]})
        # Re-posting the same cell adds nothing.
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/fog/explore",
            json={"cells": [[4, 4]]})
        assert r.status_code == 200, r.text
        assert r.json()["added"] == 0
        assert sorted(r.json()["fog_explored"]) == [[4, 4]]
    finally:
        await _reset(gm_client, mid)


async def test_player_can_explore(gm_client, alice_client):
    """Players drive exploration by moving — the /explore path is member-open,
    not GM-gated (unlike the fog PUT / reset)."""
    mid = await _active_map_id(gm_client)
    try:
        r = await alice_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/fog/explore",
            json={"cells": [[7, 7]]})
        assert r.status_code == 200, r.text
        assert [7, 7] in r.json()["fog_explored"]
    finally:
        await _reset(gm_client, mid)


async def test_reset_requires_gm_and_clears(gm_client, alice_client, gm_ws):
    mid = await _active_map_id(gm_client)
    try:
        await gm_client.post(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/fog/explore",
                             json={"cells": [[1, 1], [2, 2]]})
        # A non-GM member cannot reset the party's explored memory.
        assert (await alice_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/fog/reset")).status_code == 403

        gm_ws.mark()   # ignore the explore broadcast above; watch the reset's.
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/fog/reset")
        assert r.status_code == 200, r.text
        assert r.json()["fog_explored"] == []
        msg = await gm_ws.wait_for("fog_update")
        assert msg["data"]["fog_explored"] == []
    finally:
        await _reset(gm_client, mid)


async def test_explore_unknown_map_404(gm_client):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/map/99999999/fog/explore",
        json={"cells": [[0, 0]]})
    assert r.status_code == 404, r.text
