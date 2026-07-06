"""v2.788.1 — FreeForm walls + wall chaining.

v2.898.0 — the two-corner Room tool became a free-polygon wall mode.
v2.911.0 — renamed ⬡ FreeForm and now an OPEN chain: 🧱 Wall places a single
two-point segment, ⬡ FreeForm chains connected segments (click the last point
again, or Esc, to finish — no need to close back to the start).
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
            gm_page.locator("#me-freeform-btn").click()  # v2.927.0 — shared FreeForm toggle
            gm_page.locator("#me-wall-btn").click()      # the active draw tool
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


def test_basic_wall_is_two_point_no_chain(gm_page: Page) -> None:
    # v2.911.0 — 🧱 Wall no longer auto-extends: 3 clicks make ONE two-point wall
    # (the 3rd click starts a fresh wall's first point, not a chained segment).
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})
        try:
            _open(gm_page, mid)
            # Right-click to keep the tool armed across placements (sticky).
            gm_page.locator("#me-wall-btn").click(button="right")
            ov = gm_page.locator("#me-overlay").bounding_box()
            gm_page.mouse.click(ov["x"] + 80, ov["y"] + 70)   # wall A start
            gm_page.mouse.click(ov["x"] + 200, ov["y"] + 70)  # wall A end → 1 wall
            gm_page.wait_for_timeout(250)
            gm_page.mouse.click(ov["x"] + 200, ov["y"] + 180)  # a NEW wall's first point
            gm_page.wait_for_timeout(250)
            ws = _walls(c, mid)
            assert len(ws) == 1, ws  # only the finished two-point wall (no chain)
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})


def test_freeform_wall_chaining(gm_page: Page) -> None:
    # v2.911.0 — chaining moved from 🧱 Wall (now a single two-point wall) to
    # ⬡ FreeForm (the open-chain tool). 3 points → 2 connected segments.
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})
        try:
            _open(gm_page, mid)
            gm_page.locator("#me-freeform-btn").click()  # v2.927.0 — shared FreeForm toggle
            gm_page.locator("#me-wall-btn").click()      # the active draw tool
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
