"""v2.921.0 — a 🪟 Window option in the Walls material dropdown draws a
see-through window, and the transparency (opacity) slider adjusts it down to a
fully open window (opacity 0)."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID, me_clear_toolbar


def _walls(c, mid):
    return c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls").json()["walls"]


def test_draw_window_from_material_dropdown(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(300)
            me_clear_toolbar(gm_page)
            gm_page.select_option("#me-wall-style", "window")
            gm_page.locator("#me-wall-btn").click()
            ov = gm_page.locator("#me-overlay").bounding_box()
            gm_page.mouse.click(ov["x"] + 120, ov["y"] + 90)
            gm_page.mouse.click(ov["x"] + 320, ov["y"] + 90)
            gm_page.wait_for_timeout(400)
            ws = _walls(c, mid)
            assert len(ws) == 1, ws
            assert ws[0]["window"] is True, ws[0]
            assert ws[0]["door"] is False and ws[0]["invisible"] is False, ws[0]
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})


def test_opacity_slider_opens_the_window(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": [
            {"id": "win", "x1": 200, "y1": 320, "x2": 700, "y2": 320,
             "style": "stone", "window": True, "opacity": 1.0}]})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(300)
            me_clear_toolbar(gm_page)
            # Select the window (double-click its hit-line) so the slider edits it.
            hit = gm_page.evaluate(
                """() => {
                    const l = [...document.querySelectorAll('#me-overlay line[stroke="transparent"]')]
                        .find(l => getComputedStyle(l).pointerEvents !== 'none');
                    const r = l.getBoundingClientRect();
                    return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
                }"""
            )
            gm_page.mouse.dblclick(hit["x"], hit["y"])
            gm_page.wait_for_timeout(200)
            # v2.930.0 — opacity is a dropdown now; pick 0% → a fully open window.
            gm_page.select_option("#me-wall-opacity", "0")
            gm_page.wait_for_timeout(400)
            w = _walls(c, mid)[0]
            assert w["opacity"] == 0, w
            assert w["window"] is True, w  # still a (now open) window
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})
