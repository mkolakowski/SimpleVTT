"""v2.760.0 — dedicated map editor: draw a wall on the editor page.

Loads the GM map editor, enters wall mode, clicks two points on the overlay,
and asserts a wall segment was saved server-side.
"""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def test_editor_draws_wall(gm_page: Page) -> None:
    errors: list[str] = []
    gm_page.on("pageerror", lambda e: errors.append(str(e)))
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            overlay = gm_page.locator("#me-overlay")
            expect(overlay).to_be_visible()

            # Enter wall mode → door checkbox appears, overlay armed.
            wall_btn = gm_page.locator("#me-wall-btn")
            wall_btn.click()
            assert wall_btn.get_attribute("aria-pressed") == "true"
            expect(gm_page.locator("#me-door-lbl")).to_be_visible()

            # Click two points on the overlay to draw a segment.
            box = overlay.bounding_box()
            assert box, "overlay should have a box"
            gm_page.mouse.click(box["x"] + 80, box["y"] + 80)
            gm_page.mouse.click(box["x"] + 200, box["y"] + 80)
            gm_page.wait_for_timeout(400)  # let the PUT settle

            walls = c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls").json()["walls"]
            assert len(walls) == 1, walls
            w = walls[0]
            assert {"x1", "y1", "x2", "y2"} <= w.keys()
            # v2.764.0 — snap is on by default, so endpoints land on the grid.
            grid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json().get("grid_size_px") or 70
            for k in ("x1", "y1", "x2", "y2"):
                assert w[k] % grid == 0, (k, w[k], grid)
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})

    assert not errors, f"JS errors: {errors}"
