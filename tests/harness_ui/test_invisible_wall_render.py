"""v2.909.0 — an invisible wall shows a faint dashed guide to the GM but nothing
to players (it still blocks sight); an embedded door on it renders with its own
material regardless."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page

from playwright.sync_api import expect

from .conftest import BASE_URL, CAMPAIGN_ID, me_clear_toolbar, tabletop_url

# The invisible-wall GM guide is drawn with this distinctive dash pattern.
GUIDE = 'line[stroke-dasharray="4 7"]'


def _guide_count(page: Page) -> int:
    return page.eval_on_selector_all(f"#wall-overlay {GUIDE}", "els => els.length")


def test_invisible_wall_is_gm_only(gm_page: Page, alice_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": [
            {"id": "iw", "x1": 300, "y1": 300, "x2": 300, "y2": 600, "invisible": True}]})
    try:
        # GM sees the faint dashed guide for the invisible wall.
        gm_page.goto(tabletop_url())
        gm_page.wait_for_selector("#wall-overlay", timeout=8000)
        gm_page.wait_for_timeout(600)
        assert _guide_count(gm_page) >= 1

        # A player sees nothing drawn for it (no guide, no wall face).
        alice_page.goto(tabletop_url())
        alice_page.wait_for_selector("#wall-overlay", timeout=8000)
        alice_page.wait_for_timeout(600)
        assert _guide_count(alice_page) == 0
    finally:
        with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
            c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})


def test_draw_invisible_wall_from_material_dropdown(gm_page: Page) -> None:
    """v2.910.0 — picking 👻 Invisible in the wall material dropdown draws an
    invisible wall (not a bogus 'invisible' material)."""
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(300)
            me_clear_toolbar(gm_page)
            gm_page.select_option("#me-wall-style", "invisible")
            gm_page.locator("#me-wall-btn").click()
            ov = gm_page.locator("#me-overlay").bounding_box()
            gm_page.mouse.click(ov["x"] + 120, ov["y"] + 90)
            gm_page.mouse.click(ov["x"] + 320, ov["y"] + 90)
            gm_page.wait_for_timeout(400)
            walls = c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls").json()["walls"]
            assert len(walls) == 1, walls
            assert walls[0]["invisible"] is True, walls[0]  # invisible, not style='invisible'
            assert walls[0]["style"] != "invisible", walls[0]
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})
