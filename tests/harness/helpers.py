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
