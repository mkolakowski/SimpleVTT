"""v2.832.0 — resize a terrain region by dragging its corner handles."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def _terrain(c, mid):
    return c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/terrain").json()["terrain"]


def test_terrain_resize_via_corner_handle(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        # A single region near the centre-ish of the map (fixed coords work for
        # any reasonably-sized demo map).
        region = {"id": "trsz", "x": 150, "y": 150, "w": 460, "h": 340, "type": "water"}
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/terrain", json={"terrain": [region]})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(400)

            # Right-click the region → the menu → "Resize (drag corners)".
            gm_page.locator(".me-terrain").first.dispatch_event("contextmenu")
            gm_page.locator("#me-ctx-menu button", has_text="Resize").click()
            gm_page.wait_for_timeout(150)

            # Four yellow corner handles appear (nw, ne, sw, se).
            handles = gm_page.locator('#me-overlay circle[fill="#ffd24a"]')
            assert handles.count() == 4, handles.count()

            w0 = _terrain(c, mid)[0]["w"]
            # Drag the SE handle (last) further down-right → width grows.
            se = handles.nth(3).bounding_box()
            hx, hy = se["x"] + se["width"] / 2, se["y"] + se["height"] / 2
            gm_page.mouse.move(hx, hy)
            gm_page.mouse.down()
            gm_page.mouse.move(hx + 120, hy + 90, steps=10)
            gm_page.mouse.up()
            gm_page.wait_for_timeout(300)

            ts = _terrain(c, mid)
            assert len(ts) == 1, ts
            assert ts[0]["w"] > w0, (w0, ts[0])
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/terrain", json={"terrain": []})
