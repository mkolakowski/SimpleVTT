"""Test-harness helpers — auth + WS collection.

See docs/plans/test-harness.md for the full design. Phase 1 ships
this module + the conftest fixtures + the vertical-slice tests
under tests/harness/test_*.py.
"""
from __future__ import annotations

import asyncio
import json
import os
import time

import httpx
import websockets

BASE_URL = os.getenv("HARNESS_BASE_URL", "http://localhost:8013")
WS_BASE_URL = BASE_URL.replace("http://", "ws://").replace("https://", "wss://")
DEFAULT_TIMEOUT = float(os.getenv("HARNESS_WS_TIMEOUT", "2.0"))


async def login_client(email: str, password: str) -> httpx.AsyncClient:
    """Log in the given user and return an httpx client with the session
    cookie persisted. Caller is responsible for closing the client.
    """
    client = httpx.AsyncClient(base_url=BASE_URL, follow_redirects=True, timeout=10.0)
    resp = await client.post("/login", data={"email": email, "password": password})
    if resp.status_code not in (200, 303):
        await client.aclose()
        raise AssertionError(f"Login failed for {email}: {resp.status_code} {resp.text[:200]}")
    return client


class WSCollector:
    """Subscribe to a campaign's WS hub and accumulate messages in the
    background. Each test can ``await collector.wait_for("weapon_attack")``
    to block until the expected broadcast lands (or fail on timeout).

    The collector spawns a background task on ``__aenter__`` that drains
    every message into ``self.messages``. The constructor + the initial
    sleep absorb the hub's two priming messages (``battle_update``,
    ``presence_update``) so they don't pollute test assertions.

    Multi-listener safe: every call to ``wait_for`` scans the buffered
    messages first, then waits for new ones. ``mark()`` resets a
    cursor so a test can assert on broadcasts fired AFTER a specific
    moment (typically right before the HTTP POST).
    """

    def __init__(self, ws: websockets.WebSocketClientProtocol):
        self.ws = ws
        self.messages: list[dict] = []
        self._task: asyncio.Task | None = None
        self._closed = False
        self._cursor = 0

    async def __aenter__(self) -> "WSCollector":
        self._task = asyncio.create_task(self._recv_loop())
        # Drain the hub's priming messages (battle_update, presence_update,
        # optionally audio_play). 300 ms is generous; the messages arrive
        # within the first ~50 ms in practice but CI latency varies.
        await asyncio.sleep(0.3)
        self.mark()
        return self

    async def __aexit__(self, *args) -> None:
        self._closed = True
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass

    async def _recv_loop(self) -> None:
        try:
            while not self._closed:
                raw = await self.ws.recv()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                self.messages.append(msg)
        except (websockets.ConnectionClosed, asyncio.CancelledError):
            pass
        except Exception as e:  # noqa: BLE001
            # Don't crash the test on a WS error — surface via the
            # next wait_for assertion instead.
            print(f"WSCollector recv_loop error: {e}")

    def mark(self) -> None:
        """Set the cursor to ``len(messages)`` so subsequent ``wait_for``
        calls only see messages received AFTER this mark."""
        self._cursor = len(self.messages)

    def buffered(self, msg_type: str | None = None) -> list[dict]:
        """Return buffered messages since the last ``mark()``,
        optionally filtered by type."""
        slice_ = self.messages[self._cursor:]
        if msg_type is None:
            return list(slice_)
        return [m for m in slice_ if m.get("type") == msg_type]

    async def wait_for(self, msg_type: str, timeout: float = DEFAULT_TIMEOUT) -> dict:
        """Block until a message of ``msg_type`` arrives after the last
        ``mark()``, or raise AssertionError on timeout. Returns the message
        dict (so the caller can assert on data shape)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            hits = self.buffered(msg_type)
            if hits:
                return hits[0]
            await asyncio.sleep(0.02)
        raise AssertionError(
            f"WS message type {msg_type!r} not received within {timeout}s. "
            f"Buffered since mark: {[m.get('type') for m in self.buffered()]}"
        )

    async def wait_for_any(self, msg_types: set[str], timeout: float = DEFAULT_TIMEOUT) -> dict:
        """Wait until ANY of the given types arrives. First match wins."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for m in self.buffered():
                if m.get("type") in msg_types:
                    return m
            await asyncio.sleep(0.02)
        raise AssertionError(
            f"None of {msg_types} arrived within {timeout}s. "
            f"Buffered: {[m.get('type') for m in self.buffered()]}"
        )


async def open_ws(client: httpx.AsyncClient, campaign_id: int) -> websockets.WebSocketClientProtocol:
    """Open a WebSocket to /ws/campaign/{cid} using the httpx client's
    session cookie. Returns the raw connection; pair with WSCollector
    for buffering.
    """
    cookies = client.cookies
    cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
    # websockets v13 legacy client uses ``extra_headers``; the new
    # asyncio client uses ``additional_headers``. We're on legacy via
    # the top-level ``websockets.connect`` (the import path that
    # everything's been using since v10). Switch to ``extra_headers``
    # to match.
    return await websockets.connect(
        f"{WS_BASE_URL}/ws/campaign/{campaign_id}",
        extra_headers={"Cookie": cookie_header},
    )


async def ensure_token_at(
    gm_client: httpx.AsyncClient, campaign_id: int, char_id: int,
    x: float, y: float,
) -> dict:
    """Put ``char_id``'s token at exactly ``(x, y)`` and **prove it landed**.

    v2.1047.3. The range-gate suites derive an expected `distance_ft`
    from a token they believe is at a known origin, so a reposition that
    silently fails turns into a baffling arithmetic assertion 200 lines
    later (CI run 31070630004: ``assert 307.1 == 350.0``,
    ``assert 332.1 == 350.0``, ``assert 32.1 == 50.0`` — all three were
    the same unnoticed no-op move).

    Two things every caller was getting wrong:

    - **The move can 409 and was never checked.** ``move_token``'s
      over-speed gate fires when a battle is active *and* the moved
      token is the active combatant — and unlike the movement-lock and
      off-turn gates, it does **not** bypass for the GM. A leftover
      battle therefore rejects the setup move. ``over_speed_confirmed``
      is the documented opt-out and is always correct for setup.
    - **The returned dict was the pre-move one**, carrying stale
      coordinates even when the move did work.

    So: place if missing, move with the gate waived, assert the call
    succeeded, then re-read and assert the coordinates really are what
    the caller asked for. Returns the fresh token dict.
    """
    async def _by_char() -> dict:
        r = await gm_client.get(f"/api/campaign/{campaign_id}/tokens")
        assert r.status_code == 200, f"token list failed: {r.text}"
        return {t.get("character_id"): t for t in r.json()["tokens"]
                if t.get("character_id")}

    tok = (await _by_char()).get(char_id)
    if not tok:
        placed = await gm_client.post(
            f"/api/campaign/{campaign_id}/character/{char_id}/place-token",
            json={"x": x, "y": y},
        )
        assert placed.status_code == 200, (
            f"place-token for char {char_id} failed: "
            f"{placed.status_code} {placed.text}")
        tok = (await _by_char()).get(char_id)
        assert tok, f"char {char_id} still has no token after place-token"

    moved = await gm_client.post(
        f"/api/campaign/{campaign_id}/token/{tok['id']}/move",
        json={
            "x": x, "y": y,
            # move_token has THREE independent 409 gates that a GM does not
            # bypass. Setup movement is bookkeeping, not a tactical
            # decision, so all of them are waived here:
            #   over_speed_cap          — the movement budget
            #   oa_confirmation_required — leaving an enemy's reach
            # (movement_locked and the off-turn check DO bypass for the GM.)
            # Missing `oa_confirmed` is what turned v2.1047.3's 1 failure
            # into 6 errors in CI run 31126181450: the assertion correctly
            # refused to proceed on a failed move, but the move was failing
            # for a gate the helper hadn't waived.
            "over_speed_confirmed": True,
            "oa_confirmed": True,
        },
    )
    assert moved.status_code == 200, (
        f"setup reposition of token {tok['id']} to ({x}, {y}) failed: "
        f"{moved.status_code} {moved.text} — the test's distance math "
        f"assumes this origin, so it would fail misleadingly later")

    fresh = (await _by_char()).get(char_id)
    assert fresh, f"char {char_id}'s token vanished after the move"
    assert (float(fresh["x"]), float(fresh["y"])) == (float(x), float(y)), (
        f"token {tok['id']} is at ({fresh['x']}, {fresh['y']}), not the "
        f"requested ({x}, {y}) — setup origin is not what the test assumes")
    return fresh


async def live_token_ids(gm_client, campaign_id) -> set:
    """Token ids that actually exist in the DB right now.

    v2.1047.7. The realtime hub's battle state is in-memory and holds a
    ``source_token_id`` per combatant. Nothing prunes a combatant when
    its token row goes away, so the two drift: CI run 31126181450 had
    the battle state pointing at token **1** while the DB's tokens were
    a different generation entirely, and every fixture that trusted
    ``source_token_id`` died in setup with
    ``404 {"detail":"Token not found"}`` (9 errors across
    ``test_battle_line_targets`` + ``test_battle_sphere_cone_targets``).

    Callers should intersect the battle state's ids with this set rather
    than assuming a combatant's token is still real.
    """
    r = await gm_client.get(f"/api/campaign/{campaign_id}/tokens")
    assert r.status_code == 200, f"token list failed: {r.text}"
    return {t["id"] for t in r.json()["tokens"] if t.get("id") is not None}


async def reset_battle_state(client: httpx.AsyncClient, campaign_id: int) -> None:
    """Best-effort reset of the realtime hub's battle state for a
    campaign — calls Start Initiative which clears every combatant's
    economy slots. Used as a per-test setup hook so action-economy
    state is predictable across tests.

    Phase 1 caveat: this requires the demo encounter to be loaded
    (so battle.combatants is non-empty). The fixture call_load_encounter
    in conftest handles the initial load.
    """
    # TODO Phase 1.5: a dedicated /test/reset_battle endpoint guarded by
    # ENV=test would be cleaner. For now we POST a battle_state with
    # everyone's chips cleared via the existing pushBattle WS path —
    # but the harness can't fire a WS message from a non-GM client
    # cleanly. As a Phase 1 workaround tests pass override:true on
    # every call and validate state mutations on the response body
    # rather than the chip state.
    pass
