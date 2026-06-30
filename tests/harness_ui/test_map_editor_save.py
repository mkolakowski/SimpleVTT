"""v2.781.0 — explicit Save button in the map editor.

Edits auto-save, but the 💾 Save button commits every layer in one click and
reports a confirmation. This draws a wall, clicks Save, and asserts the
confirmation status + that the wall persists.
"""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def test_save_button_commits(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(400)
            # Draw a wall (two clicks in wall mode).
            gm_page.locator("#me-wall-btn").click()
            ov = gm_page.locator("#me-overlay").bounding_box()
            gm_page.mouse.click(ov["x"] + 80, ov["y"] + 80)
            gm_page.mouse.click(ov["x"] + 220, ov["y"] + 80)
            gm_page.wait_for_timeout(200)

            # Explicit Save → confirmation status.
            gm_page.locator("#me-save-btn").click()
            expect(gm_page.locator("#me-status")).to_contain_text("saved", ignore_case=True)

            assert len(c.get(
                f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls").json()["walls"]) >= 1
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})
