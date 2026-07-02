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
            # Wait for the image load → fitContain (sets the initial fit zoom).
            gm_page.wait_for_function(
                "() => window.__lightCanvasForTest !== undefined || true")
            gm_page.wait_for_timeout(500)

            def _zoom_pct():
                return int(gm_page.locator("#me-zoom-lbl").inner_text().rstrip("%"))
            before = _zoom_pct()
            # Zoom in three times → the displayed zoom % must increase.
            for _ in range(3):
                gm_page.locator("#me-zoom-in").click()
            assert _zoom_pct() > before, (before, _zoom_pct())

            # Draw a wall at the zoomed scale, in the lower-centre of the stage
            # (v2.838.0 — clear of the floating toolbar; the zoomed map fills it).
            gm_page.locator("#me-wall-btn").click()
            box = gm_page.locator("#me-stage").bounding_box()
            wy = box["y"] + box["height"] * 0.7
            gm_page.mouse.click(box["x"] + box["width"] * 0.4, wy)
            gm_page.mouse.click(box["x"] + box["width"] * 0.4 + 130, wy)
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


def test_scroll_wheel_zooms(gm_page: Page) -> None:
    """v2.830.0 — the scroll wheel zooms the map in and out."""
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
    expect(gm_page.locator("#me-overlay")).to_be_visible()
    gm_page.wait_for_timeout(400)

    def _pct() -> int:
        return int(gm_page.locator("#me-zoom-lbl").inner_text().rstrip("%"))

    box = gm_page.locator("#me-stage").bounding_box()
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    gm_page.mouse.move(cx, cy)

    before = _pct()
    # Wheel up (negative deltaY) zooms in.
    for _ in range(3):
        gm_page.mouse.wheel(0, -120)
        gm_page.wait_for_timeout(40)
    zoomed_in = _pct()
    assert zoomed_in > before, (before, zoomed_in)

    # Wheel down (positive deltaY) zooms back out.
    for _ in range(3):
        gm_page.mouse.wheel(0, 120)
        gm_page.wait_for_timeout(40)
    assert _pct() < zoomed_in, (zoomed_in, _pct())
