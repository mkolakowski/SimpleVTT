"""v2.846.0 — GM fog perspective on the tabletop.

The GM sees **no fog by default** (the whole map is visible); only when the GM
**targets** an entity does the fog render from that entity's viewpoint — the
target's wall-occluded vision clear, explored ground dimmed, everything else
opaque. Driven through the ``window.__testDrawFog`` hook (``gm`` / ``targetIds``
overrides) and sampled via ``window.__fogCanvasForTest``.
"""
from __future__ import annotations

from playwright.sync_api import Page

from .conftest import BASE_URL, CAMPAIGN_ID


def test_gm_sees_no_fog_without_a_target(gm_page: Page) -> None:
    errors: list[str] = []
    gm_page.on("pageerror", lambda e: errors.append(str(e)))
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
    gm_page.wait_for_function("() => window.__testDrawFog", timeout=8000)

    # GM, dynamic fog, a hero token + some explored ground, but NO target.
    no_fog = gm_page.evaluate("""() => {
        const g = 70;
        window.__testDrawFog({
            gm: true, dynamic: true, walls: [],
            tokens: [{ id: 1, x: 2*g, y: 2*g, size: 1, team: 'hero',
                       light_bright_ft: 0, light_dim_ft: 0 }],
            explored: [[5, 5]],
        });
        // drawFog() returns before touching the fog canvas → it's never set.
        return window.__fogCanvasForTest == null;
    }""")
    assert no_fog, "GM with no target should see no fog overlay at all"
    assert not errors, f"JS errors: {errors}"


def test_gm_targeting_shows_that_entitys_view(gm_page: Page) -> None:
    errors: list[str] = []
    gm_page.on("pageerror", lambda e: errors.append(str(e)))
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
    gm_page.wait_for_function("() => window.__testDrawFog", timeout=8000)

    # GM targets token 1 (at cell 2,2). A wall at x=5g occludes the right side.
    # Cell (3,2) is in the target's view → clear; (7,2) is behind the wall but
    # explored → dim memory; (7,3) is behind the wall, never seen → opaque.
    res = gm_page.evaluate("""() => {
        const g = 70;
        window.__testDrawFog({
            gm: true, targetIds: [1], dynamic: true,
            walls: [{ x1: 5*g, y1: 0, x2: 5*g, y2: 6*g }],
            tokens: [{ id: 1, x: 2*g, y: 2*g, size: 1, team: 'hero',
                       light_bright_ft: 0, light_dim_ft: 0 }],
            explored: [[7, 2]],
        });
        const cx = window.__fogCanvasForTest.getContext('2d');
        const cell = (c, r) => cx.getImageData(c*g + g/2, r*g + g/2, 1, 1).data[3];
        return { front: cell(3, 2), memory: cell(7, 2), unseen: cell(7, 3) };
    }""")
    assert res["front"] < 40, res            # target sees it → clear
    assert 60 < res["memory"] < 200, res     # explored, occluded → dim
    assert res["unseen"] > 200, res          # never seen → opaque
    assert not errors, f"JS errors: {errors}"
