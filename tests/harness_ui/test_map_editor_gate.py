"""v2.787.1 — gates (open in the middle), door/gate orientation flip, and
click-anywhere toggling.
"""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def _walls(c, mid):
    return c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls").json()["walls"]


def _open(gm_page, mid):
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
    expect(gm_page.locator("#me-overlay")).to_be_visible()
    gm_page.wait_for_timeout(300)


def _hit_box(gm_page):
    return gm_page.locator('#me-overlay line[stroke="transparent"]').first.bounding_box()


def test_convert_to_gate_and_flip(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": [
            {"id": "w", "x1": 200, "y1": 200, "x2": 340, "y2": 200, "style": "wood"}]})
        try:
            _open(gm_page, mid)
            box = _hit_box(gm_page)
            cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
            # Wall → Gate via the Type submenu.
            gm_page.mouse.click(cx, cy, button="right")
            gm_page.locator("#me-ctx-menu button", has_text="Type").hover()
            gm_page.locator(".me-ctx-fly button", has_text="Gate").click()
            gm_page.wait_for_timeout(300)
            assert _walls(c, mid)[0]["gate"] is True, _walls(c, mid)
            # Flip swing.
            gm_page.mouse.click(cx, cy, button="right")
            gm_page.locator("#me-ctx-menu button", has_text="Flip").click()
            gm_page.wait_for_timeout(300)
            assert _walls(c, mid)[0]["flip"] is True, _walls(c, mid)
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})


def test_open_door_leaf_click_closes(gm_page: Page) -> None:
    # v2.787.1 — click-anywhere: clicking the swung-open leaf toggles it shut.
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        # A vertical open door: hinge (200,200), leaf swings to ~ (340,200) area.
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": [
            {"id": "d", "x1": 200, "y1": 200, "x2": 200, "y2": 340,
             "door": True, "open": True, "style": "wood"}]})
        try:
            _open(gm_page, mid)
            # There are two transparent hit-lines now (opening + swung leaf);
            # click the leaf one (second) which sits away from the opening.
            hits = gm_page.locator('#me-overlay line[stroke="transparent"]')
            assert hits.count() >= 2, hits.count()
            b = hits.nth(1).bounding_box()
            gm_page.mouse.click(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)
            gm_page.wait_for_timeout(300)
            assert _walls(c, mid)[0]["open"] is False, _walls(c, mid)
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})
