"""v2.788.4 — hex grid in the map editor (overlay + persistence)."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def test_editor_hex_grid(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.post(f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/grid_type",
               json={"grid_type": "square"})
        editor = f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit"
        try:
            gm_page.goto(editor)
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(400)
            # Square by default → no hex polygons.
            assert gm_page.locator("#me-overlay polygon").count() == 0
            # Switch to Hex → hex polygons render + it persists.
            gm_page.select_option("#me-grid-type", "hex")
            gm_page.wait_for_timeout(400)
            assert gm_page.locator("#me-overlay polygon").count() > 10
            assert c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["grid_type"] == "hex"
            gm_page.reload()
            gm_page.wait_for_timeout(500)
            assert gm_page.locator("#me-grid-type").input_value() == "hex"
            assert gm_page.locator("#me-overlay polygon").count() > 10
        finally:
            c.post(f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/grid_type",
                   json={"grid_type": "square"})
