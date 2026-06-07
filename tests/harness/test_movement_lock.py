"""v2.102.0 — campaign movement lock.

When the GM locks movement (`POST /movement_lock {locked: true}`),
non-GM token drags are rejected by `/token/move` with a 409
`movement_locked`; GM drags pass through (the GM is the arbiter). The
toggle broadcasts `movement_lock_update` so every client's lock chrome
+ player-drag gating stays in sync.

The lock gate sits BEFORE the v2.99.79 turn-enforcement gate in
`move_token`, so it fires first regardless of battle state — but these
tests still clear any active battle up front so the unlocked control
move isn't turn-gated, and always unlock in a `finally` so a failure
mid-test doesn't strand the demo campaign locked for the rest of the
suite.

Tests:
  - happy path: GM locks → 200 + `movement_lock_update(locked=true)`;
    player move → 409 `movement_locked`; GM move still 200; unlock →
    player move 200.
  - error path: non-GM `POST /movement_lock` → 403.
"""
import asyncio

from .conftest import CAMPAIGN_ID


async def _pip_token(client, pip_id):
    resp = await client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")
    assert resp.status_code == 200, resp.text
    for t in resp.json()["tokens"]:
        if t.get("character_id") == pip_id:
            return t
    raise AssertionError(f"no token for Pip ({pip_id}) in tokens list")


async def _clear_battle(gm_client):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [], "round": 0, "turn_index": 0, "active": False},
    )


async def test_movement_lock_blocks_player_gm_passes(
    gm_client, alice_client, gm_ws, roster,
):
    """GM lock blocks alice's drag of her own PC (Pip) with 409
    movement_locked, the lock toggle broadcasts movement_lock_update,
    the GM can still move, and unlocking restores the player move."""
    pip = roster["Pip Quickfingers"]  # owned by alice
    await _clear_battle(gm_client)
    tok = await _pip_token(gm_client, pip["id"])
    x0, y0 = float(tok["x"]), float(tok["y"])
    try:
        # Lock (GM).
        gm_ws.mark()
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/movement_lock",
            json={"locked": True},
        )
        assert r.status_code == 200, r.text
        assert r.json() == {"ok": True, "locked": True}
        msg = await gm_ws.wait_for("movement_lock_update")
        assert msg["data"]["locked"] is True

        # Player drag is rejected.
        blocked = await alice_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/token/{tok['id']}/move",
            json={"x": x0 + 70, "y": y0},
        )
        assert blocked.status_code == 409, blocked.text
        body = blocked.json()
        assert body["error"] == "movement_locked"
        assert body["token_id"] == tok["id"]

        # GM drag passes through (arbiter).
        gm_move = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/token/{tok['id']}/move",
            json={"x": x0 + 70, "y": y0},
        )
        assert gm_move.status_code == 200, gm_move.text

        # Unlock → player drag works again.
        u = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/movement_lock",
            json={"locked": False},
        )
        assert u.status_code == 200, u.text
        assert u.json()["locked"] is False
        await asyncio.sleep(0.1)
        ok = await alice_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/token/{tok['id']}/move",
            json={"x": x0, "y": y0},
        )
        assert ok.status_code == 200, ok.text
    finally:
        # Never strand the campaign locked for the rest of the suite.
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/movement_lock",
            json={"locked": False},
        )


async def test_movement_lock_requires_gm(alice_client):
    """A non-GM player cannot toggle the movement lock — 403."""
    r = await alice_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/movement_lock",
        json={"locked": True},
    )
    assert r.status_code == 403, (
        f"non-GM movement_lock toggle must be rejected; got {r.status_code}"
    )
