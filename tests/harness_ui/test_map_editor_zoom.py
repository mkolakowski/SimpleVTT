"""v2.767.0 — map editor zoom.

Zooming changes the displayed size but `getScreenCTM` keeps click→map coords
correct: after zooming in, drawing a wall still lands on grid-aligned map
coords (snap on).
"""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def test_zoom_keeps_drawing_correct(gm_page: Page) -> None:
    errors: list[str] = []
    gm_page.on("pageerror", lambda e: errors.append(str(e)))
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        grid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json().get("grid_size_px") or 70
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()

            # Zoom in twice.
            gm_page.locator("#me-zoom-in").click()
            gm_page.locator("#me-zoom-in").click()
            lbl = gm_page.locator("#me-zoom-lbl").inner_text()
            assert lbl.rstrip("%").isdigit() and int(lbl.rstrip("%")) > 100, lbl

            # Draw a wall at the zoomed scale.
            gm_page.locator("#me-wall-btn").click()
            box = gm_page.locator("#me-overlay").bounding_box()
            gm_page.mouse.click(box["x"] + 90, box["y"] + 90)
            gm_page.mouse.click(box["x"] + 220, box["y"] + 90)
            gm_page.wait_for_timeout(400)

            walls = c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls").json()["walls"]
            assert len(walls) == 1, walls
            w = walls[0]
            # Coords are in map (natural) space + grid-aligned despite the zoom.
            for k in ("x1", "y1", "x2", "y2"):
                assert w[k] % grid == 0, (k, w[k], grid)
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})

    assert not errors, f"JS errors: {errors}"
