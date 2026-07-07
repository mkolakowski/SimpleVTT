"""v2.952.0 — token movement collision: tokens can't pass through solid walls
or closed doors (open embedded doors leave a gap).

Tests the geometry clamp (`window.__clampMoveToWallsForTest`) directly: a move
crossing a wall / closed gate is clamped to just before it; a move through an
OPEN gate, or one that doesn't cross, is unblocked. (Player-vs-GM gating lives
in `_applyWallCollision`; the GM places freely.)
"""
from __future__ import annotations

from playwright.sync_api import Page

from .conftest import BASE_URL, CAMPAIGN_ID


def test_move_blocked_by_wall_and_closed_door_not_open(gm_page: Page) -> None:
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
    gm_page.wait_for_function("() => window.__clampMoveToWallsForTest && window._setMapWalls",
                              timeout=10000)

    r = gm_page.evaluate(
        """() => {
            const C = window.__clampMoveToWallsForTest;
            // A horizontal wall at y=600 with an embedded gate over x∈[400,550].
            window._setMapWalls([{ id: 'w', x1: 0, y1: 600, x2: 1000, y2: 600,
                doors: [{ id: 'd', t0: 0.4, t1: 0.55, gate: true, open: false }] }]);
            const closedGate = C(500, 800, 500, 300);  // up through the CLOSED gate
            const solidPart  = C(100, 800, 100, 300);  // up through the solid wall
            const along      = C(200, 800, 800, 800);  // parallel, never crosses
            // Now open the gate → the gap lets the token through.
            window._setMapWalls([{ id: 'w', x1: 0, y1: 600, x2: 1000, y2: 600,
                doors: [{ id: 'd', t0: 0.4, t1: 0.55, gate: true, open: true }] }]);
            const openGate = C(500, 800, 500, 300);
            window._setMapWalls([]);
            return { closedGate, solidPart, along, openGate };
        }"""
    )
    # Crossing a closed gate / solid wall is blocked and clamped to the near side.
    assert r["closedGate"]["blocked"] is True, r
    assert 600 < r["closedGate"]["y"] < 800, r      # stopped just below the wall
    assert r["solidPart"]["blocked"] is True, r
    # An open gate leaves a gap; a parallel move never crosses → both unblocked.
    assert r["openGate"]["blocked"] is False, r
    assert r["along"]["blocked"] is False, r
