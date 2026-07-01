"""v2.790.1 — placing GM-only pins in the map editor."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def test_place_gm_pin(gm_page: Page) -> None:
    answers = iter(["Trap", "DC 15 Dex, 3d6 fire"])
    gm_page.on("dialog", lambda d: d.accept(next(answers, "")))
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/gm_pins", json={"gm_pins": []})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(400)
            gm_page.locator("#me-pin-btn").click()
            ov = gm_page.locator("#me-overlay").bounding_box()
            gm_page.mouse.click(ov["x"] + 120, ov["y"] + 90)
            gm_page.wait_for_timeout(300)
            pins = c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/gm_pins").json()["gm_pins"]
            assert len(pins) == 1, pins
            assert pins[0]["label"] == "Trap" and pins[0]["note"] == "DC 15 Dex, 3d6 fire"
            assert gm_page.locator("#me-overlay circle.me-gmpin").count() == 1
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/gm_pins", json={"gm_pins": []})
