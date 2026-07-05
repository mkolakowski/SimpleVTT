"""v2.916.0 — GM token right-click context menu on the tabletop.

Right-clicking a token as the GM opens an action menu (open sheet · resize ·
hide/show · delete) instead of jumping straight to the sheet. This test places
a token, right-clicks it, and uses the menu's size control to resize it.
"""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def test_gm_right_click_token_menu_resizes(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        am = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()
        w = int(am.get("width_px") or 2000)
        h = int(am.get("height_px") or 1500)
        # Place a token near the map centre (most likely on-screen after auto-fit).
        cx_map, cy_map = w / 2, h / 2
        tok = c.post(f"/api/campaign/{CAMPAIGN_ID}/tokens",
                     json={"label": "CtxTest", "x": cx_map, "y": cy_map, "size": 1}).json()
        tid = tok["id"]
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
            gm_page.wait_for_selector("#token-veil-canvas", timeout=8000)
            gm_page.wait_for_function("() => window.__camScaleForTest", timeout=8000)
            gm_page.wait_for_timeout(500)

            # Compute the token centre's client position from the map transform.
            pt = gm_page.evaluate(
                """([mx, my]) => {
                    const scale = window.__camScaleForTest();
                    const g = parseInt(document.getElementById('vtt-canvas').dataset.gridSize || '70', 10);
                    const rect = document.getElementById('map-transform').getBoundingClientRect();
                    return { x: rect.left + (mx + g / 2) * scale, y: rect.top + (my + g / 2) * scale };
                }""",
                [cx_map, cy_map],
            )
            # Right-click the token → the GM context menu opens.
            gm_page.mouse.click(pt["x"], pt["y"], button="right")
            menu = gm_page.locator(".tt-token-ctx")
            expect(menu).to_be_visible(timeout=3000)
            # It carries the size segmented control + the hide/delete actions.
            expect(menu.get_by_role("button", name="L", exact=True)).to_be_visible()

            # Click "L" (size 2) → the token resizes.
            menu.get_by_role("button", name="L", exact=True).click()
            gm_page.wait_for_timeout(500)
            after = c.get(f"/api/campaign/{CAMPAIGN_ID}/tokens").json()["tokens"]
            row = next(t for t in after if t["id"] == tid)
            assert row["size"] == 2, row
            # The menu closed after the action.
            expect(menu).to_have_count(0)
        finally:
            c.request("DELETE", f"/api/campaign/{CAMPAIGN_ID}/tokens/{tid}")
