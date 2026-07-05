"""v2.917.0 — large-token footprint snapping + scale-aware hit target.

  * A dropped token snaps so its N×N footprint sits squarely on cells: odd
    sizes (1, 3) land on a grid line (unchanged from the old snap); even sizes
    (2, 4) land on a half-cell offset so the block doesn't straddle cells.
  * The right-click / drag hit radius now matches the drawn radius (which
    includes the per-map token_scale), so you can click what you see.
"""
from __future__ import annotations

from playwright.sync_api import Page

from .conftest import BASE_URL, CAMPAIGN_ID


def _boot(gm_page: Page) -> None:
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
    gm_page.wait_for_selector("#token-veil-canvas", timeout=8000)
    gm_page.wait_for_function("() => window.__snapTokenFootprintForTest", timeout=8000)
    gm_page.wait_for_timeout(300)


def test_footprint_snap_aligns_by_parity(gm_page: Page) -> None:
    _boot(gm_page)
    res = gm_page.evaluate(
        """() => {
            const g = window.__gridSizeForTest();
            const snap = window.__snapTokenFootprintForTest;
            const x = 7.3 * g + 11, y = 4.6 * g - 9;  // deliberately off-grid
            const mod = (v) => ((v % g) + g) % g;
            const out = { g };
            for (const n of [1, 2, 3, 4]) {
                const [sx, sy] = snap(x, y, n);
                // Footprint top-left corner = centre - N*g/2.
                const flx = (sx + g / 2) - n * g / 2;
                out[n] = { sxMod: mod(sx), flxMod: mod(flx) };
            }
            return out;
        }"""
    )
    g = res["g"]

    def near(v, target):
        # mod values wrap, so "on a grid line" is ~0 or ~g.
        return abs(v - target) < 0.01 or abs(v - target - g) < 0.01 or abs(v - target + g) < 0.01

    for n in (1, 2, 3, 4):
        # Every size: the footprint's top-left lands on a grid line.
        assert near(res[str(n)]["flxMod"], 0), (n, res[str(n)])
    # Odd sizes → token origin on a grid line; even sizes → half-cell offset.
    assert near(res["1"]["sxMod"], 0), res["1"]
    assert near(res["2"]["sxMod"], g / 2), res["2"]
    assert near(res["3"]["sxMod"], 0), res["3"]
    assert near(res["4"]["sxMod"], g / 2), res["4"]


def test_hit_radius_tracks_drawn_radius(gm_page: Page) -> None:
    _boot(gm_page)
    res = gm_page.evaluate(
        """() => {
            const g = window.__gridSizeForTest();
            const t = { x: 500, y: 500, size: 2 };
            const cx = t.x + g / 2, cy = t.y + g / 2;
            const rad = window.__tokenRadiusForTest(t);
            return {
                inside: window.__pointInTokenForTest(cx + rad * 0.8, cy, t),
                outside: window.__pointInTokenForTest(cx + rad * 1.3, cy, t),
            };
        }"""
    )
    assert res["inside"] is True, res
    assert res["outside"] is False, res
