"""WS-frame collector for the encounter-sim suite.

Hooks Playwright's ``page.on("websocket")`` event so the test
observes the SAME broadcasts the browser sees — no separate
connection that could race against the GM page's. Frames are
parsed (JSON) and pushed into a list; tests call ``wait_for(type)``
to poll until a matching frame arrives.

Plan reference: ``docs/plans/encounter-sim-test-suite.md`` —
"Output validation strata", layer 2 (WS broadcast).
"""
from __future__ import annotations

import json
from typing import Any, Callable

from playwright.sync_api import Page


class WSCollector:
    """Collect every WS frame the page receives during the test.

    Usage:
        ws = WSCollector(gm_page)
        ws.start()
        gm_page.goto(...)              # browser opens WS, collector hooks
        # ... do something that triggers a broadcast
        frame = ws.wait_for("weapon_attack")
        assert frame["data"]["actor_character_id"] == ...
    """

    def __init__(self, page: Page) -> None:
        self.page = page
        self.frames: list[dict[str, Any]] = []
        self._on_ws: Callable[..., None] | None = None

    def start(self) -> None:
        """Install the page-level websocket listener. Must be called
        BEFORE the page navigation that opens the WS — Playwright's
        ``page.on("websocket")`` only fires for sockets opened after
        the listener is registered.
        """
        def _on_ws(ws):
            ws.on("framereceived", self._on_frame)
        self._on_ws = _on_ws
        self.page.on("websocket", _on_ws)

    def _on_frame(self, payload: str) -> None:
        # Server frames are JSON like {"type": "weapon_attack", "data": {...}}.
        # Pings + other non-JSON traffic gets ignored silently.
        try:
            obj = json.loads(payload)
        except (ValueError, TypeError):
            return
        if isinstance(obj, dict):
            self.frames.append(obj)

    def wait_for(
        self,
        type_name: str,
        timeout_ms: int = 3000,
        predicate: Callable[[dict], bool] | None = None,
    ) -> dict[str, Any]:
        """Block until a frame with ``type == type_name`` arrives
        (optionally also matching ``predicate(frame)``), else raise.

        The poll loop uses ``page.wait_for_timeout`` between checks
        rather than ``time.sleep`` — the latter blocks Playwright's
        sync-API event loop, so the ``framereceived`` listener can't
        fire and frames arrive only after the loop times out. The
        Playwright wait yields to the event loop so listeners run.

        Returns the first matching frame. Does not consume it from
        the buffer — repeat callers see the same frame, so callers
        wanting "next matching frame after this point" should
        snapshot ``len(self.frames)`` before triggering and slice.
        """
        elapsed = 0
        step_ms = 50
        while elapsed < timeout_ms:
            for f in self.frames:
                if f.get("type") != type_name:
                    continue
                if predicate is None or predicate(f):
                    return f
            self.page.wait_for_timeout(step_ms)
            elapsed += step_ms
        raise AssertionError(
            f"WS frame type={type_name!r} not seen within {timeout_ms}ms. "
            f"Captured types: {[f.get('type') for f in self.frames]}"
        )

    def buffered(self, type_name: str) -> list[dict[str, Any]]:
        """All buffered frames of a given type. Useful for asserting
        absence (``assert not ws.buffered('weapon_attack')``) or
        counting (``assert len(ws.buffered('roll')) == 3``).
        """
        return [f for f in self.frames if f.get("type") == type_name]
