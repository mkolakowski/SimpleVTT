"""v2.953.0 — wall vision shadows reach fully past the map edge.

A token below a wide horizontal wall must not see the FAR side of it. The wall
shadow projects each endpoint away from the token; for a wide wall directly
above/below the token those rays are nearly horizontal, so a short reach left the
far top of the map lit (vision leaked past the wall as a token approached it).
The reach is now long enough to cover the whole far side.
"""
from __future__ import annotations

from playwright.sync_api import Page

from .conftest import BASE_URL, CAMPAIGN_ID


def test_wide_wall_shadow_hides_far_side(alice_page: Page) -> None:
    alice_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
    alice_page.wait_for_function("() => window.__testDrawFog && window.ME", timeout=10000)

    r = alice_page.evaluate(
        """() => {
            const g = 70;
            // A full-width solid wall at y=600; a token I control just below it.
            const out = window.__testDrawFog({
                dynamic: true,
                walls: [{ x1: 0, y1: 600, x2: 4000, y2: 600 }],
                tokens: [{ id: 1, x: 900, y: 660, size: 1,
                           controller_user_id: window.ME.id,
                           light_bright_ft: 0, light_dim_ft: 0 }],
                explored: [],
            });
            const vis = new Set(out.visible);
            return {
                belowWall: vis.has('13,9'),   // token side of the wall → seen
                justAbove: vis.has('13,8'),   // far side, near → hidden
                farTop: vis.has('13,1'),      // far side, top of map → hidden
            };
        }"""
    )
    assert r["belowWall"] is True, r     # the token sees its own side
    assert r["justAbove"] is False, r    # the wall blocks the near far-side
    assert r["farTop"] is False, r       # …and the whole far side, not just a band
