"""Canvas reader — pixel-sample helpers for canvas-only checks like
the 💀 skull overlay (v2.49.4) or AoE persistent markers.

See ``docs/plans/encounter-sim-test-suite.md``. Methods grow as
Level 3 tests need them — Phase 4 commit O lights up
``token_center_pixel`` and ``has_skull_overlay_for_token`` for the
v2.49.4 regression class that motivated this whole suite.

The page's canvas is at ``#tabletop-canvas``; its 2d context is
read via ``page.evaluate`` so the test process never touches
Playwright's image-extraction APIs (lighter + more reliable than
screenshot-then-PIL).
"""
from __future__ import annotations

from playwright.sync_api import Page


class CanvasReader:
    def __init__(self, page: Page) -> None:
        self.page = page

    def pixel_at(self, x: float, y: float) -> list[int] | None:
        """Sample the canvas at the given coords. Returns ``[r, g,
        b, a]`` (0-255 each) or ``None`` if the canvas isn't on
        the page.

        Reads from ``#vtt-canvas`` via ``getImageData(x, y, 1, 1)``
        on the existing 2D context — no re-render, no screenshot.
        Coords are in CANVAS space (the same coord space the
        token's ``x`` / ``y`` fields live in), not viewport.
        """
        return self.page.evaluate(
            """({cx, cy}) => {
                const canvas = document.getElementById('vtt-canvas');
                if (!canvas) return null;
                const ctx = canvas.getContext('2d');
                const data = ctx.getImageData(
                    Math.round(cx), Math.round(cy), 1, 1
                ).data;
                return [data[0], data[1], data[2], data[3]];
            }""",
            {"cx": x, "cy": y},
        )

    def grid_size(self) -> int:
        """Return the active map's grid cell size in canvas pixels.
        Read from ``#vtt-canvas[data-grid-size]`` set server-side
        from the active_map row.
        """
        return int(
            self.page.evaluate(
                "() => parseInt(document.getElementById('vtt-canvas')"
                ".dataset.gridSize || '70', 10)"
            )
        )

    def pixel_at_token_center(self, token: dict) -> list[int] | None:
        """Sample the center pixel of a token. ``token`` is a dict
        from ``helpers.battle.find_token_for_character`` (or the
        ``/api/campaign/{cid}/tokens`` payload directly) — uses
        ``token["x"]`` / ``token["y"]`` and the active map's grid
        size.
        """
        gs = self.grid_size()
        size = int(token.get("size") or 1)
        cx = float(token["x"]) + (gs * size) / 2.0
        cy = float(token["y"]) + (gs * size) / 2.0
        return self.pixel_at(cx, cy)

    def has_skull_overlay_at_token(self, token: dict) -> bool:
        """Heuristic: is the v2.49.4 skull overlay drawn over the
        token? The skull renders as a 💀 emoji centered on the token
        with a white fill + 3px black stroke, sitting on top of a
        ``rgba(0,0,0,0.55)`` dim circle. Sampling the very center
        pixel typically hits the emoji glyph — either the white
        fill (very high RGB sum) or the black stroke (very low sum).
        A normal portrait pixel lands in the mid-range; this
        heuristic flags the saturated case as "skull-y".
        """
        rgba = self.pixel_at_token_center(token)
        if rgba is None:
            return False
        r, g, b, _ = rgba
        total = r + g + b
        return total >= 700 or total <= 60
