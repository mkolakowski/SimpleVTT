"""v2.940.0 — an invisible wall is drawn as a clearly-visible glowing dashed
"ghost" guide in the map editor (was a thin faint 2px line)."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def test_invisible_wall_has_visible_ghost_guide(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": [
            {"id": "iw", "x1": 200, "y1": 300, "x2": 700, "y2": 300, "invisible": True}]})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(400)

            r = gm_page.evaluate(
                """() => {
                    const lines = [...document.querySelectorAll('#me-overlay line')];
                    // Bright dashed core (8 6) + a wide halo (>=8px), both bluish.
                    const core = lines.some(l => l.getAttribute('stroke-dasharray') === '8 6');
                    const halo = lines.some(l => parseFloat(l.getAttribute('stroke-width')) >= 8);
                    return { core, halo };
                }"""
            )
            assert r["core"], "expected a bright dashed core for the invisible wall"
            assert r["halo"], "expected a wide halo stroke for the invisible wall"
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})
