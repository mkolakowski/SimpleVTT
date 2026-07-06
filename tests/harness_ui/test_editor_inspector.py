"""v2.926.0 — Theme B: a floating "Selected object" inspector. Double-click a
wall and the panel shows its editable properties (material / opacity / type /
flip / secret / delete); edits round-trip and Delete removes it."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID, me_clear_toolbar


def _walls(c, mid):
    return c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls").json()["walls"]


def _select_wall(gm_page: Page) -> None:
    hit = gm_page.evaluate(
        """() => {
            const l = [...document.querySelectorAll('#me-overlay line[stroke="transparent"]')]
                .find(l => getComputedStyle(l).pointerEvents !== 'none');
            const r = l.getBoundingClientRect();
            return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
        }"""
    )
    gm_page.mouse.dblclick(hit["x"], hit["y"])
    gm_page.wait_for_timeout(250)


def test_wall_inspector_edits(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": [
            {"id": "w", "x1": 200, "y1": 320, "x2": 700, "y2": 320, "style": "stone", "opacity": 1.0}]})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(300)
            me_clear_toolbar(gm_page)

            insp = gm_page.locator("#me-inspector")
            expect(insp).to_be_hidden()
            _select_wall(gm_page)
            expect(insp).to_be_visible()
            assert "selected · wall" in gm_page.locator("#me-insp-title").inner_text().lower()

            # Material → wood.
            gm_page.locator("#me-insp-body select").first.select_option("wood")
            gm_page.wait_for_timeout(300)
            assert _walls(c, mid)[0]["style"] == "wood"

            # Opacity slider → 40%.
            sld = gm_page.locator('#me-insp-body input[type="range"]')
            sld.fill("40")
            sld.dispatch_event("input")
            gm_page.wait_for_timeout(300)
            assert _walls(c, mid)[0]["opacity"] == 0.4

            # Type → Door; the title follows.
            gm_page.locator('#me-insp-body button[title="door"]').click()
            gm_page.wait_for_timeout(300)
            assert _walls(c, mid)[0]["door"] is True
            assert "selected · door" in gm_page.locator("#me-insp-title").inner_text().lower()
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})


def test_wall_inspector_delete(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": [
            {"id": "w", "x1": 200, "y1": 320, "x2": 700, "y2": 320, "style": "stone"}]})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(300)
            me_clear_toolbar(gm_page)
            _select_wall(gm_page)
            expect(gm_page.locator("#me-inspector")).to_be_visible()

            gm_page.locator("#me-insp-body button", has_text="Delete").click()
            gm_page.wait_for_timeout(400)
            assert _walls(c, mid) == []
            expect(gm_page.locator("#me-inspector")).to_be_hidden()
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})
