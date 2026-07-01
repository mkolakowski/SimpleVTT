"""v2.788.1 — room tool (4 walls in one shot) + polyline wall chaining."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def _walls(c, mid):
    return c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls").json()["walls"]


def _open(gm_page, mid):
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
    expect(gm_page.locator("#me-overlay")).to_be_visible()
    gm_page.wait_for_timeout(400)


def test_room_tool_makes_four_walls(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})
        try:
            _open(gm_page, mid)
            gm_page.locator("#me-room-btn").click()
            ov = gm_page.locator("#me-overlay").bounding_box()
            gm_page.mouse.click(ov["x"] + 90, ov["y"] + 70)     # corner 1
            gm_page.mouse.click(ov["x"] + 260, ov["y"] + 190)   # opposite corner
            gm_page.wait_for_timeout(300)
            assert len(_walls(c, mid)) == 4, _walls(c, mid)  # four sides
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
