"""v2.904.0 — an OPEN embedded door is clicked/right-clicked on its swung leaf,
not the empty doorway it left behind. The editor builds the door's hit-line from
``doorLeafSegments`` (which follows the leaf), so on a horizontal wall an open
door yields a hit-line with vertical extent (the leaf swings off the wall)."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID, me_clear_toolbar


def test_open_embedded_door_hitline_follows_the_leaf(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        # A horizontal wall with one OPEN embedded door in the middle.
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": [
            {"id": "w", "x1": 200, "y1": 300, "x2": 700, "y2": 300,
             "doors": [{"id": "d1", "t0": 0.4, "t1": 0.6, "open": True}]}]})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(300)
            me_clear_toolbar(gm_page)

            # Collect the interactive door hit-lines (transparent, clickable,
            # with a Door/Gate tooltip) and their vertical extent.
            geom = gm_page.evaluate(
                """() => {
                    const lines = [...document.querySelectorAll('#me-overlay line[stroke="transparent"]')];
                    return lines.filter(l => {
                        const t = l.querySelector('title');
                        return t && /Door|Gate/.test(t.textContent)
                            && getComputedStyle(l).pointerEvents === 'stroke';
                    }).map(l => ({
                        y1: +l.getAttribute('y1'), y2: +l.getAttribute('y2'),
                    }));
                }"""
            )
            assert geom, "expected an interactive door hit-line"
            # The open door's leaf swings perpendicular to the horizontal wall,
            # so its hit-line has real vertical extent (not lying along y=300).
            assert any(abs(g["y1"] - g["y2"]) > 20 for g in geom), geom
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})
