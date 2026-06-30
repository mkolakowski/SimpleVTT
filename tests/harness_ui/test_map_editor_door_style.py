"""v2.772.0 — map editor: dedicated 🚪 Door button + wall/door style picker.

Doors are drawn via their own button (not a checkbox), and new segments carry
the selected material style. Verifies a drawn door persists with door=true +
the chosen style.
"""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def test_draw_door_with_style(gm_page: Page) -> None:
    errors: list[str] = []
    gm_page.on("pageerror", lambda e: errors.append(str(e)))
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()

            # Pick a material + the dedicated Door tool.
            gm_page.select_option("#me-wall-style", "wood")
            door_btn = gm_page.locator("#me-door-btn")
            expect(door_btn).to_be_visible()
            door_btn.click()
            assert door_btn.get_attribute("aria-pressed") == "true"

            # Draw a door (two clicks).
            box = gm_page.locator("#me-overlay").bounding_box()
            gm_page.mouse.click(box["x"] + 100, box["y"] + 100)
            gm_page.mouse.click(box["x"] + 220, box["y"] + 100)
            gm_page.wait_for_timeout(400)

            walls = c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls").json()["walls"]
            assert len(walls) == 1, walls
            assert walls[0]["door"] is True
            assert walls[0]["style"] == "wood"
            # The door renders with a knob (circle) in the overlay.
            assert gm_page.locator("#me-overlay circle").count() >= 1
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})

    assert not errors, f"JS errors: {errors}"
