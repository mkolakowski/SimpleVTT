"""v2.844.0 — exploration-tracking fog of war (client three-state render).

Drives the deterministic ``window.__testDrawFog`` hook with a known token, a
wall, and an explored set, then samples ``window.__fogCanvasForTest`` (pure
map-pixel coords) to assert the three fog states:

  - a cell the party token currently sees → fully clear (low alpha),
  - a cell behind a wall that was previously explored → dimmed memory (mid),
  - a cell behind the wall that was never seen → opaque veil (high alpha).

Using a wall to put the memory/unseen cells out of current view keeps the test
independent of the live map's exact pixel size (both sit a few cells from the
token, well inside any canvas).
"""
from __future__ import annotations

from playwright.sync_api import Page

from .conftest import BASE_URL, CAMPAIGN_ID


def test_dynamic_fog_three_states(alice_page: Page) -> None:
    errors: list[str] = []
    alice_page.on("pageerror", lambda e: errors.append(str(e)))

    alice_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
    alice_page.wait_for_function("() => window.__testDrawFog && window.ME", timeout=8000)

    # Grid 70px. A token alice OWNS at cell (2,2) (v2.945.0 — players see only
    # through their own tokens). A solid vertical wall at x=5*g occludes
    # everything to its right on that band. Cell (3,2) is in front (visible);
    # cells (7,2)/(7,3) are behind the wall (not currently visible). Pre-mark
    # (7,2) as explored → dim memory; (7,3) is never seen → opaque.
    res = alice_page.evaluate("""() => {
        const g = 70;
        const fc = window.__fogCellForTest();       // v2.954.0 — finer fog cells
        const key = (px, py) => Math.floor(px / fc) + ',' + Math.floor(py / fc);
        const front = [3*g + g/2, 2*g + g/2];       // in front of the wall
        const memory = [7*g + g/2, 2*g + g/2];      // behind the wall (pre-explored)
        const out = window.__testDrawFog({
            dynamic: true,
            walls: [{ x1: 5*g, y1: 0, x2: 5*g, y2: 6*g }],
            tokens: [{ id: 1, x: 2*g, y: 2*g, size: 1, team: 'hero',
                       controller_user_id: window.ME.id,
                       light_bright_ft: 0, light_dim_ft: 0 }],
            explored: [[Math.floor(memory[0] / fc), Math.floor(memory[1] / fc)]],
        });
        const cx = window.__fogCanvasForTest.getContext('2d');
        const cell = (p) => cx.getImageData(p[0], p[1], 1, 1).data[3];
        return {
            visible: out.visible,
            frontKey: key(front[0], front[1]), memoryKey: key(memory[0], memory[1]),
            frontAlpha: cell(front),        // in front of wall → currently visible
            memoryAlpha: cell(memory),      // behind wall, explored → dim memory
            unseenAlpha: cell([7*g + g/2, 3*g + g/2]),  // behind wall, never seen → opaque
        };
    }""")

    assert res["frontKey"] in res["visible"], res      # front cell is in the live set
    assert res["memoryKey"] not in res["visible"], res  # wall occludes the memory cell
    # Player veil ~0.97 (alpha ~247). Visible clears fully; memory partial (0.6
    # erase → ~99); unseen stays opaque.
    assert res["frontAlpha"] < 40, res
    assert 60 < res["memoryAlpha"] < 200, res
    assert res["unseenAlpha"] > 200, res

    assert not errors, f"JS errors: {errors}"
