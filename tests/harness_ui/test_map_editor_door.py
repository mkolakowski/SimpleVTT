"""v2.786.7 — doors render as hinged doors + carry a hover tooltip with state."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID, me_clear_toolbar


def test_door_visual_and_tooltip(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": [
            {"id": "d", "x1": 200, "y1": 200, "x2": 200, "y2": 340,
             "door": True, "open": False, "style": "wood"}]})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(300)
            me_clear_toolbar(gm_page)  # map is full-bleed behind the toolbar
            # A swing arc (path) is drawn for the door.
            assert gm_page.locator("#me-overlay path").count() >= 1
            # The hit-line carries a <title> describing the door + its state.
            title = gm_page.eval_on_selector(
                '#me-overlay line[stroke="transparent"] title', "e => e.textContent")
            assert "Door" in title and "closed" in title, title
            # Toggle open → tooltip flips to "open".
            box = gm_page.locator('#me-overlay line[stroke="transparent"]').first.bounding_box()
            gm_page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            gm_page.wait_for_timeout(300)
            title2 = gm_page.eval_on_selector(
                '#me-overlay line[stroke="transparent"] title', "e => e.textContent")
            assert "open" in title2, title2
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})
