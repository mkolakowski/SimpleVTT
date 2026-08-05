"""v2.1044.0 — presence idle state on the ``presence_update`` broadcast.

The hub now stamps every presence entry with how long that user has been
quiet (``idle_seconds``) and whether that crosses the campaign threshold
(``idle``), and puts the threshold itself on the payload
(``idle_after_seconds``). The client ages ``idle_seconds`` forward locally
between broadcasts, so these fields ARE the contract the UI reads — a
regression here silently freezes every seat as "active".

Covered here:

- **Happy path** — connecting produces a ``presence_update`` whose users
  carry the new fields, with the connecting user active (not idle) and the
  threshold echoed on the payload.
- **Activity ping** — an inbound WS frame is accepted and keeps the sender
  active. This is the contract behind ``hub.mark_active``; the server must
  not choke on the client's ``{"type": "activity"}`` frame (before
  v2.1044.0 the receive loop discarded every frame, so a malformed handler
  here would break the socket for everything else too).
- **Multi-tab fold** — two sockets for the same user still yield ONE
  presence row (the dedupe predates this change and is easy to break, since
  the idle merge had to replace the old ``continue``-on-duplicate).
- **Error path** — a junk frame that isn't JSON doesn't kill the socket or
  drop the user from presence. The receive loop hands every frame to
  ``mark_active`` without parsing it, so garbage must be harmless.

Idle *expiry* itself (a seat actually going amber) is deliberately NOT
tested end-to-end: the threshold is 300 s and no endpoint injects a clock,
so asserting it would mean a 5-minute sleep. The pieces that are testable
without a time machine — the field contract, the active case, and the
merge — are covered here; the threshold arithmetic is a one-line
comparison against ``PRESENCE_IDLE_AFTER_SECONDS`` in ``get_presence``.
"""
from __future__ import annotations

import json

import pytest

from .conftest import CAMPAIGN_ID
from .helpers import WSCollector, open_ws


def _me(users: list[dict], user_id: int) -> dict | None:
    for u in users:
        if u.get("user_id") == user_id:
            return u
    return None


async def _presence_payload(collector: WSCollector) -> dict:
    """The most recent presence_update payload seen by this collector,
    scanning the whole buffer (the priming roster arrives during
    __aenter__, i.e. before the test's mark())."""
    hits = [m for m in collector.messages if m.get("type") == "presence_update"]
    assert hits, (
        "no presence_update buffered; got "
        f"{[m.get('type') for m in collector.messages]}"
    )
    return hits[-1].get("data") or {}


async def test_presence_update_carries_idle_fields(gm_client, gm_ws):
    """Happy path: the roster shape the client reads."""
    data = await _presence_payload(gm_ws)

    assert "users" in data, f"presence payload missing 'users': {data}"
    users = data["users"]
    assert isinstance(users, list) and users, f"empty presence roster: {data}"

    # The threshold rides on the payload so the client can age the clock
    # locally without hardcoding the server's constant.
    assert isinstance(data.get("idle_after_seconds"), (int, float)), (
        f"missing/invalid idle_after_seconds: {data}"
    )
    assert data["idle_after_seconds"] > 0

    for u in users:
        assert "idle" in u, f"user row missing 'idle': {u}"
        assert isinstance(u["idle"], bool), f"'idle' must be a bool: {u}"
        assert "idle_seconds" in u, f"user row missing 'idle_seconds': {u}"
        assert isinstance(u["idle_seconds"], (int, float)), (
            f"'idle_seconds' must be numeric: {u}"
        )
        assert u["idle_seconds"] >= 0, f"negative idle_seconds: {u}"
        # The pre-existing fields must survive the shape change.
        assert "user_id" in u and "display_name" in u and "is_gm" in u, u

    # The GM just connected, so they are unambiguously active.
    gm_rows = [u for u in users if u.get("is_gm")]
    assert gm_rows, f"no GM in presence roster: {users}"
    assert not gm_rows[0]["idle"], f"freshly-connected GM marked idle: {gm_rows[0]}"
    assert gm_rows[0]["idle_seconds"] < 60, (
        f"freshly-connected GM has a stale idle clock: {gm_rows[0]}"
    )


async def test_activity_frame_is_accepted_and_keeps_user_active(gm_client):
    """An inbound activity frame is consumed by hub.mark_active and the
    socket stays healthy + the sender stays active."""
    ws = await open_ws(gm_client, CAMPAIGN_ID)
    try:
        async with WSCollector(ws) as collector:
            # The client's real ping, verbatim.
            await ws.send(json.dumps({"type": "activity"}))
            # A second connect on the same campaign forces a fresh roster
            # broadcast so we can read post-ping state.
            ws2 = await open_ws(gm_client, CAMPAIGN_ID)
            try:
                msg = await collector.wait_for("presence_update", timeout=5.0)
            finally:
                await ws2.close()

            users = (msg.get("data") or {}).get("users") or []
            assert users, f"empty roster after activity ping: {msg}"
            for u in users:
                if u.get("is_gm"):
                    assert not u["idle"], f"active GM marked idle: {u}"
    finally:
        await ws.close()


async def test_multiple_tabs_yield_one_presence_row(gm_client):
    """Two sockets for one user still dedupe to a single row.

    The idle merge replaced the old ``continue``-on-duplicate-uid, so this
    guards the dedupe that change had to preserve.
    """
    ws1 = await open_ws(gm_client, CAMPAIGN_ID)
    try:
        async with WSCollector(ws1) as collector:
            ws2 = await open_ws(gm_client, CAMPAIGN_ID)
            try:
                msg = await collector.wait_for("presence_update", timeout=5.0)
                users = (msg.get("data") or {}).get("users") or []
                assert users, f"empty roster: {msg}"
                ids = [u.get("user_id") for u in users]
                assert len(ids) == len(set(ids)), (
                    f"duplicate user rows with two tabs open: {ids}"
                )
            finally:
                await ws2.close()
    finally:
        await ws1.close()


async def test_garbage_frame_does_not_break_the_socket(gm_client):
    """Error path: a non-JSON frame is harmless.

    The receive loop passes frames to mark_active without parsing, so junk
    must neither raise nor drop the connection from presence.
    """
    ws = await open_ws(gm_client, CAMPAIGN_ID)
    try:
        async with WSCollector(ws) as collector:
            await ws.send("not json at all {{{")
            # Socket must still be usable afterwards.
            await ws.send(json.dumps({"type": "activity"}))
            ws2 = await open_ws(gm_client, CAMPAIGN_ID)
            try:
                msg = await collector.wait_for("presence_update", timeout=5.0)
            finally:
                await ws2.close()
            users = (msg.get("data") or {}).get("users") or []
            assert users, (
                f"socket dropped out of presence after a junk frame: {msg}"
            )
    finally:
        await ws.close()
