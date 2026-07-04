"""v2.788.1 — free-polygon walls + polyline wall chaining.

v2.898.0 — the two-corner Room tool became a free-polygon wall mode: click a
chain of vertices, then click the first dot to close it into a loop of walls.
"""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID, me_clear_toolbar


def _walls(c, mid):
    return c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls").json()["walls"]


def _open(gm_page, mid):
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
    expect(gm_page.locator("#me-overlay")).to_be_visible()
    gm_page.wait_for_timeout(400)
    me_clear_toolbar(gm_page)  # map is full-bleed behind the toolbar


def test_free_polygon_walls_close_into_a_loop(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})
        try:
            _open(gm_page, mid)
            gm_page.locator("#me-room-btn").click()  # ⬡ Free polygon (walls)
            ov = gm_page.locator("#me-overlay").bounding_box()
            corners = [(90, 70), (260, 70), (260, 190), (90, 190)]
            for (dx, dy) in corners:
                gm_page.mouse.click(ov["x"] + dx, ov["y"] + dy)
                gm_page.wait_for_timeout(120)
            # Click the FIRST dot again to close the loop → 4 wall segments.
            gm_page.mouse.click(ov["x"] + corners[0][0], ov["y"] + corners[0][1])
            gm_page.wait_for_timeout(300)
            assert len(_walls(c, mid)) == 4, _walls(c, mid)  # closed 4-gon
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})


def test_wall_chaining(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})
        try:
            _open(gm_page, mid)
            gm_page.locator("#me-wall-btn").click()
            ov = gm_page.locator("#me-overlay").bounding_box()
            # Chain of 3 points → 2 connected segments (no tool re-click
            # between). Small waits let each per-segment save land in order.
            gm_page.mouse.click(ov["x"] + 80, ov["y"] + 70)
            gm_page.wait_for_timeout(150)
            gm_page.mouse.click(ov["x"] + 200, ov["y"] + 70)
            gm_page.wait_for_timeout(200)
            gm_page.mouse.click(ov["x"] + 200, ov["y"] + 180)
            gm_page.wait_for_timeout(300)
            ws = _walls(c, mid)
            assert len(ws) == 2, ws
            # The second segment starts where the first ended (connected chain).
            assert (ws[1]["x1"], ws[1]["y1"]) == (ws[0]["x2"], ws[0]["y2"]), ws
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})
