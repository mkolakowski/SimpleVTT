"""v2.901.0 — embedded doors P3: the tabletop renders a wall with a ``doors``
list as its plain-wall face spans + a door glyph per embedded door, and each
door's hit-line toggles it open/closed by the composite {wallId}:{doorId} id."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID, tabletop_url


def test_embedded_door_renders_and_toggles(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        # A vertical wall carrying one embedded door in its middle.
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": [
            {"id": "ew", "x1": 400, "y1": 250, "x2": 400, "y2": 550,
             "doors": [{"id": "d1", "t0": 0.35, "t1": 0.65, "open": False}]}]})
        try:
            gm_page.goto(tabletop_url())
            gm_page.wait_for_selector("#wall-overlay", timeout=8000)
            gm_page.wait_for_timeout(600)

            # The door glyph draws its brass knob dot (#f0d060).
            expect(gm_page.locator('#wall-overlay circle[fill="#f0d060"]').first).to_be_attached()

            # A clickable door hit-line exists for the embedded door; dispatching
            # a click on it toggles the door (via the composite-id endpoint).
            fired = gm_page.evaluate(
                """() => {
                    const lines = [...document.querySelectorAll('#wall-overlay line[stroke="transparent"]')];
                    const dh = lines.find(l => {
                        const t = l.querySelector('title');
                        return t && /Door/.test(t.textContent)
                            && getComputedStyle(l).pointerEvents === 'stroke';
                    });
                    if (!dh) return false;
                    dh.dispatchEvent(new MouseEvent('click', { bubbles: true }));
                    return true;
                }"""
            )
            assert fired, "no clickable embedded-door hit-line found"
            gm_page.wait_for_timeout(700)  # let the toggle POST + walls_update land

            walls = c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls").json()["walls"]
            w = next(w for w in walls if w["id"] == "ew")
            assert w["doors"][0]["open"] is True, w  # the embedded door opened
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})
