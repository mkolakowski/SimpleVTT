"""v2.860.0 — the tabletop fits the whole map into the viewport on load.

Regression guard for the "tokens off-screen on a large map" bug: the map used
to render at 1:1 from the top-left, so a map taller/wider than the viewport left
its lower/right content (incl. tokens) off-screen. Now the whole map fits
(centred, scaled down as needed) on first load.
"""
from __future__ import annotations

from playwright.sync_api import Page

from .conftest import BASE_URL, CAMPAIGN_ID


def test_whole_map_fits_viewport(gm_page: Page) -> None:
    # The flagship map (1254×1254) is taller than the default 720px viewport,
    # so at 1:1 its bottom would be cut off — the fit must scale it down.
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
    gm_page.wait_for_selector("#wall-overlay", timeout=8000)
    gm_page.wait_for_timeout(600)

    r = gm_page.evaluate("""() => {
        const wrap = document.getElementById('map-transform');
        const pane = document.getElementById('map-pane');
        const bg = document.getElementById('map-bg-layer');
        const pr = pane.getBoundingClientRect();
        const br = bg.getBoundingClientRect();  // rendered (transformed) map box
        return {
            hasTransform: !!wrap.style.transform,
            paneW: pr.width, paneH: pr.height,
            mapW: br.width, mapH: br.height,
            mapTop: br.top - pr.top, mapBottom: br.bottom - pr.top,
        };
    }""")
    assert r["hasTransform"], "a fit transform should be applied on load"
    # The whole map fits within the pane (with a small tolerance for margins).
    assert r["mapW"] <= r["paneW"] + 2, r
    assert r["mapH"] <= r["paneH"] + 2, r
    # And its full vertical extent is on-screen (the bug left the bottom off).
    assert r["mapTop"] >= -2 and r["mapBottom"] <= r["paneH"] + 2, r
