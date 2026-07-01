"""v2.790.2 — the GM sees GM-only pins on the live tabletop."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def test_gm_sees_pins_on_tabletop(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/gm_pins", json={"gm_pins": [
            {"id": "p1", "x": 300, "y": 240, "label": "Trap", "note": "DC 15"}]})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
            gm_page.wait_for_function(
                "() => typeof window._onGmPinsChanged === 'function'", timeout=8000)
            # The GM fetches + renders the pin (amber marker).
            expect(gm_page.locator("#wall-overlay circle.tt-gmpin")).to_have_count(1, timeout=8000)
            # Live update via the data-less signal → re-fetch shows two.
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/gm_pins", json={"gm_pins": [
                {"id": "p1", "x": 300, "y": 240, "label": "Trap", "note": "DC 15"},
                {"id": "p2", "x": 500, "y": 400, "label": "Lever", "note": "opens gate"}]})
            expect(gm_page.locator("#wall-overlay circle.tt-gmpin")).to_have_count(2, timeout=8000)
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/gm_pins", json={"gm_pins": []})
