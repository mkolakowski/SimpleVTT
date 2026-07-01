"""v2.789.1 — painting terrain regions in the map editor."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def _terrain(c, mid):
    return c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/terrain").json()["terrain"]


def test_paint_terrain_region(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/terrain", json={"terrain": []})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(400)
            gm_page.locator("#me-terrain-btn").click()          # terrain mode
            gm_page.select_option("#me-terrain-type", "water")
            ov = gm_page.locator("#me-overlay").bounding_box()
            # Drag a rectangle near the visible top-left.
            gm_page.mouse.move(ov["x"] + 70, ov["y"] + 60)
            gm_page.mouse.down()
            gm_page.mouse.move(ov["x"] + 210, ov["y"] + 150, steps=6)
            gm_page.mouse.up()
            gm_page.wait_for_timeout(300)
            ts = _terrain(c, mid)
            assert len(ts) == 1 and ts[0]["type"] == "water", ts
            assert gm_page.locator("#me-overlay rect.me-terrain").count() == 1
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/terrain", json={"terrain": []})
