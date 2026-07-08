"""v2.964.1 — the map editor's door right-click menu exposes the "🎲 Open check"
submenu (v2.963.0), so a GM can require an ability/skill check + DC to open a
door. This locks the editor reachability of the feature (the server round-trip
+ enforcement live in tests/harness/test_door_open_check.py)."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID, me_clear_toolbar


def test_door_menu_has_open_check(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": [
            {"id": "dw", "x1": 200, "y1": 300, "x2": 700, "y2": 300,
             "door": True, "open": False}]})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(300)
            me_clear_toolbar(gm_page)

            # Right-click the door (no tool active) → its context menu.
            box = gm_page.locator('#me-overlay line[stroke="transparent"]').first.bounding_box()
            gm_page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2,
                                button="right")
            menu = gm_page.locator("#me-ctx-menu")
            expect(menu).to_be_visible()
            # The "🎲 Open check" item is only added for doors/gates.
            expect(menu.locator("button", has_text="Open check")).to_be_visible()
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})
