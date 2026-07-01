"""v2.792.0 — placing decorative prop stamps in the map editor."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def test_place_prop(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/props", json={"props": []})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(400)
            # Pick the tree glyph, arm the prop tool, click the map.
            gm_page.select_option("#me-prop-kind", "🌲")
            gm_page.locator("#me-prop-btn").click()
            ov = gm_page.locator("#me-overlay").bounding_box()
            gm_page.mouse.click(ov["x"] + 140, ov["y"] + 110)
            gm_page.wait_for_timeout(300)
            props = c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/props").json()["props"]
            assert len(props) == 1, props
            assert props[0]["kind"] == "🌲"
            assert props[0]["size"] == 40.0 and props[0]["rot"] == 0.0
            # The glyph renders as an SVG <text> in the overlay.
            assert gm_page.locator("#me-overlay text").count() >= 1
            # Hiding the Props layer removes the glyph text + its hit box.
            gm_page.uncheck("#me-layer-props")
            gm_page.wait_for_timeout(200)
            assert gm_page.locator('#me-overlay text', has_text="🌲").count() == 0
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/props", json={"props": []})


def test_place_image_prop(gm_page: Page) -> None:
    """v2.795.0 — an ``img:`` prop renders as an SVG <image>, not a glyph."""
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/props", json={"props": []})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(400)
            gm_page.select_option("#me-prop-kind", "img:barrel")
            gm_page.locator("#me-prop-btn").click()
            ov = gm_page.locator("#me-overlay").bounding_box()
            gm_page.mouse.click(ov["x"] + 160, ov["y"] + 130)
            gm_page.wait_for_timeout(300)
            props = c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/props").json()["props"]
            assert len(props) == 1 and props[0]["kind"] == "img:barrel", props
            im = gm_page.locator("#me-overlay image")
            assert im.count() == 1
            assert "barrel.svg" in (im.first.get_attribute("href") or "")
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/props", json={"props": []})
