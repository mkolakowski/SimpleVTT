"""v2.757.0 — Maps 2.0 wall shadows in the client lighting overlay.

On a dark map, a light source is occluded by walls: a point behind a wall
(relative to the light) stays veiled while a point the light reaches directly
is cleared. Driven deterministically via `window.__testDrawLighting`, which
composites the lighting layer for a known ambient + light emitter + wall set;
the harness then samples `window.__lightCanvasForTest` (pure map-pixel coords).
"""
from __future__ import annotations

from playwright.sync_api import Page

from .conftest import BASE_URL, CAMPAIGN_ID


def test_wall_casts_shadow_in_lighting(gm_page: Page) -> None:
    errors: list[str] = []
    gm_page.on("pageerror", lambda e: errors.append(str(e)))
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
    gm_page.wait_for_function(
        "() => typeof window.__testDrawLighting === 'function'", timeout=8000)

    # Dark map, one daylight emitter at (535,535) r60, a vertical wall at
    # x=620 between the light and the east side.
    out = gm_page.evaluate("""() => window.__testDrawLighting(
        'dark',
        [{ kind: 'daylight', x: 535, y: 535, radius_ft: 60 }],
        [{ x1: 620, y1: 350, x2: 620, y2: 750 }])""")
    assert out is True, out  # drawLighting didn't throw

    res = gm_page.evaluate("""() => {
        const cv = window.__lightCanvasForTest;
        const cx = cv.getContext('2d');
        const a = (x, y) => cx.getImageData(x, y, 1, 1).data[3];
        return {
            center: a(540, 535),  // at the light — cleared
            lit: a(580, 535),     // west of the wall, reached by the light
            shadow: a(720, 535),  // east of the wall, occluded
        };
    }""")
    # The light clears its own area; the point behind the wall stays veiled.
    assert res["center"] < 60, res
    assert res["shadow"] > res["lit"] + 40, res
    assert res["shadow"] > 120, res

    # And with the wall removed, the same far point becomes lit.
    gm_page.evaluate("""() => window.__testDrawLighting(
        'dark', [{ kind: 'daylight', x: 535, y: 535, radius_ft: 60 }], [])""")
    open_alpha = gm_page.evaluate("""() => {
        const cx = window.__lightCanvasForTest.getContext('2d');
        return cx.getImageData(720, 535, 1, 1).data[3];
    }""")
    assert open_alpha < 120, open_alpha  # no wall → the point is now lit

    assert not errors, f"JS errors: {errors}"
