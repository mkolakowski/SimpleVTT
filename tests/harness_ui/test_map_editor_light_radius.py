"""v2.857.0 — drag a selected light's bright/dim radius rings to resize them.

A placed light is auto-selected; a selected light's bright + dim rings carry
draggable ft-labelled handles. Dragging the dim handle outward grows `dim_ft`
and flips the light's type to `custom`.
"""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID, me_clear_toolbar


def _lights(c, mid):
    return c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights").json()["lights"]


def test_place_auto_selects_and_shows_handles(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights", json={"lights": []})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(400)
            # Enter light mode + place one by clicking the stage.
            gm_page.click("#me-light-btn")
            box = gm_page.locator("#me-overlay").bounding_box()
            gm_page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] * 0.55)
            gm_page.wait_for_timeout(400)
            assert len(_lights(c, mid)) == 1
            # Auto-selected → at least one yellow radius handle is shown.
            assert gm_page.locator('#me-overlay circle[fill="#ffd24a"]').count() >= 1
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights", json={"lights": []})


def test_drag_dim_radius_grows_and_customises(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights", json={"lights": [
            {"id": "rad", "x": 420, "y": 420, "bright_ft": 20, "dim_ft": 40,
             "color": "#ffb347", "color2": "#ff7a1a", "type": "torch"}]})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(400)
            me_clear_toolbar(gm_page)  # map is full-bleed behind the toolbar
            # Select the light → bright + dim handles appear.
            gm_page.locator(".me-light").first.dblclick()
            gm_page.wait_for_timeout(200)
            handles = gm_page.locator('#me-overlay circle[fill="#ffd24a"]')
            assert handles.count() == 2, handles.count()

            # The dim handle is the outer one (larger x); drag it further out.
            boxes = []
            for i in range(handles.count()):
                bb = handles.nth(i).bounding_box()
                boxes.append((bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2))
            outer = max(boxes, key=lambda p: p[0])
            gm_page.mouse.move(outer[0], outer[1])
            gm_page.mouse.down()
            gm_page.mouse.move(outer[0] + 120, outer[1], steps=10)
            gm_page.mouse.up()
            gm_page.wait_for_timeout(300)

            L = _lights(c, mid)[0]
            assert L["dim_ft"] > 40, L
            assert L["type"] == "custom", L
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights", json={"lights": []})
