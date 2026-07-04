"""v2.896.0 — pressing Delete removes the single dbl-click-selected object."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID, me_clear_toolbar


def test_delete_key_removes_selected_wall(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": [
            {"id": "w", "x1": 200, "y1": 200, "x2": 360, "y2": 200, "style": "stone"}]})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(300)
            me_clear_toolbar(gm_page)

            # Double-click the wall's hit-line to select it.
            box = gm_page.locator('#me-overlay line[stroke="transparent"]').first.bounding_box()
            gm_page.mouse.dblclick(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            gm_page.wait_for_timeout(200)

            # Press Delete → the selected wall is removed + persisted.
            gm_page.keyboard.press("Delete")
            gm_page.wait_for_timeout(400)
            walls = c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls").json()["walls"]
            assert walls == [], walls
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})
