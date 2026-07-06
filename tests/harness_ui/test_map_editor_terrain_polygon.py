"""v2.855.0 — free-polygon terrain (unlimited segments).

With the "Free polygon" toggle on, terrain is placed by clicking vertices and
closing on the first point (min 3). Asserts a 5-vertex region saves with 5
`points`, and that it renders as an SVG polygon on the live tabletop.
"""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def _terrain(c, mid):
    return c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/terrain").json()["terrain"]


def test_free_polygon_placement(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/terrain", json={"terrain": []})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(400)

            # Enable the free-polygon toggle (also flips into terrain mode).
            gm_page.click("#me-terrain-btn")   # arm the terrain tool
            gm_page.click("#me-freeform-btn")  # v2.927.0 — shared FreeForm toggle
            assert gm_page.get_attribute("#me-freeform-btn", "aria-pressed") == "true"

            # Click 5 vertices around a pentagon over the stage's lower half,
            # then click the first vertex again to close.
            box = gm_page.locator("#me-overlay").bounding_box()
            cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] * 0.6
            pts = [(-120, -70), (120, -70), (150, 60), (0, 120), (-150, 60)]
            for dx, dy in pts:
                gm_page.mouse.click(cx + dx, cy + dy)
                gm_page.wait_for_timeout(110)
            # Close on the first vertex.
            gm_page.mouse.click(cx + pts[0][0], cy + pts[0][1])
            gm_page.wait_for_timeout(400)

            ts = _terrain(c, mid)
            assert len(ts) == 1, ts
            assert len(ts[0].get("points") or []) == 5, ts[0]
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/terrain", json={"terrain": []})


def test_polygon_renders_on_tabletop(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/terrain", json={"terrain": [
            {"id": "pent", "type": "water",
             "points": [[200, 200], [400, 220], [440, 400], [300, 480], [180, 360]]},
        ]})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
            gm_page.wait_for_selector("#wall-overlay", timeout=8000)
            gm_page.wait_for_timeout(700)
            # The 5-point region renders as an SVG <polygon> in the map overlay.
            n = gm_page.evaluate(
                "() => document.querySelectorAll('#wall-overlay polygon').length")
            assert n >= 1, n
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/terrain", json={"terrain": []})
