"""v2.906.0 — "Insert door here" in a wall's right-click menu embeds a door at
the click point (no Door tool needed; the wall stays one object)."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID, me_clear_toolbar


def test_insert_door_via_wall_context_menu(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": [
            {"id": "w", "x1": 200, "y1": 300, "x2": 700, "y2": 300, "style": "stone"}]})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(300)
            me_clear_toolbar(gm_page)

            # Right-click the wall (no tool active) → context menu.
            box = gm_page.locator('#me-overlay line[stroke="transparent"]').first.bounding_box()
            gm_page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2,
                                button="right")
            menu = gm_page.locator("#me-ctx-menu")
            expect(menu).to_be_visible()
            insert = menu.locator("button", has_text="Insert door")
            expect(insert).to_be_visible()
            insert.click()
            gm_page.wait_for_timeout(400)

            walls = c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls").json()["walls"]
            assert len(walls) == 1, walls  # still one wall
            assert len(walls[0].get("doors", [])) == 1, walls[0]  # with an embedded door
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})
