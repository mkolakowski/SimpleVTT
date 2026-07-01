"""v2.788.0 — undo / redo for the map editor's persisted layers."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def _walls(c, mid):
    return c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls").json()["walls"]


def test_undo_redo_wall(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(400)
            # Draw one wall.
            gm_page.locator("#me-wall-btn").click()
            ov = gm_page.locator("#me-overlay").bounding_box()
            gm_page.mouse.click(ov["x"] + 100, ov["y"] + 80)
            gm_page.mouse.click(ov["x"] + 250, ov["y"] + 80)
            gm_page.wait_for_timeout(300)
            assert len(_walls(c, mid)) == 1, _walls(c, mid)
            # Undo → gone.
            expect(gm_page.locator("#me-undo-btn")).to_be_enabled()
            gm_page.locator("#me-undo-btn").click()
            gm_page.wait_for_timeout(400)
            assert len(_walls(c, mid)) == 0, _walls(c, mid)
            # Redo → back.
            expect(gm_page.locator("#me-redo-btn")).to_be_enabled()
            gm_page.locator("#me-redo-btn").click()
            gm_page.wait_for_timeout(400)
            assert len(_walls(c, mid)) == 1, _walls(c, mid)
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})
