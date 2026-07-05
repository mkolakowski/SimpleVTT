"""v2.909.0 — an invisible wall shows a faint dashed guide to the GM but nothing
to players (it still blocks sight); an embedded door on it renders with its own
material regardless."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page

from .conftest import BASE_URL, CAMPAIGN_ID, tabletop_url

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
