"""v2.769.0 — map editor grid overlay + controls.

The editor draws a grid overlay (toggleable) and exposes grid size + offset
controls; changing the size persists (and re-renders the overlay).
"""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def test_editor_grid_overlay_and_controls(gm_page: Page) -> None:
    errors: list[str] = []
    gm_page.on("pageerror", lambda e: errors.append(str(e)))
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        # Ensure grid is on for a deterministic start.
        c.post(f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/show_grid",
               json={"show_grid": True})
        c.post(f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/grid_size",
               json={"grid_size_px": 70, "grid_offset_x": 0, "grid_offset_y": 0})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()

            # Grid lines render (inside a <g>, distinct from wall <line>s).
            grid_lines = gm_page.locator("#me-overlay g line")
            assert grid_lines.count() > 0, grid_lines.count()

            # Toggling grid off removes the overlay lines.
            gm_page.locator("#me-grid-show").click()
            assert gm_page.locator("#me-overlay g line").count() == 0
            gm_page.locator("#me-grid-show").click()  # back on
            assert gm_page.locator("#me-overlay g line").count() > 0

            # Changing the grid size persists as grid_size_px (was a no-op bug).
            gm_page.fill("#me-grid", "100")
            gm_page.locator("#me-grid").dispatch_event("change")
            gm_page.wait_for_timeout(400)
            am = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()
            assert am["grid_size_px"] == 100, am
        finally:
            c.post(f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/grid_size",
                   json={"grid_size_px": 70, "grid_offset_x": 0, "grid_offset_y": 0})

    assert not errors, f"JS errors: {errors}"
