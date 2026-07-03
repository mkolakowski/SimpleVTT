"""v2.854.0 — the "Select & move" editor toggle.

On by default: double-clicking an object selects it and makes it drag-to-move;
walls/doors/terrain also light up their resize handles. Toggling it off leaves
the double-click select-to-edit (toolbar mirror) but drops drag + handles.
"""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def _lights(c, mid):
    return c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights").json()["lights"]


def test_toggle_default_on_and_drag_and_resize(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        saved_walls = c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls").json()["walls"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights", json={"lights": [
            {"id": "sm-l", "x": 420, "y": 420, "bright_ft": 20, "dim_ft": 20,
             "color": "#ffb347", "color2": "#ff7a1a", "type": "torch"}]})
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": [
            {"id": "sm-w", "x1": 300, "y1": 300, "x2": 700, "y2": 300, "style": "stone"}]})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(400)

            # Toggle is lit by default.
            assert gm_page.get_attribute("#me-selmove-btn", "aria-pressed") == "true"

            # Double-click the light → select → drag its body → saved x/y moves.
            light = gm_page.locator(".me-light").first
            light.dblclick()
            gm_page.wait_for_timeout(150)
            b0 = _lights(c, mid)[0]
            bb = light.bounding_box()
            hx, hy = bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2
            gm_page.mouse.move(hx, hy)
            gm_page.mouse.down()
            gm_page.mouse.move(hx + 160, hy + 120, steps=10)
            gm_page.mouse.up()
            gm_page.wait_for_timeout(300)
            b1 = _lights(c, mid)[0]
            assert (b1["x"], b1["y"]) != (b0["x"], b0["y"]), (b0, b1)

            # Double-click the wall → resize handles (2 end handles) light up.
            # (dispatch_event bypasses the visibility check on the zero-height
            # transparent hit line.)
            gm_page.locator("#me-overlay line[stroke='transparent']").first.dispatch_event("dblclick")
            gm_page.wait_for_timeout(150)
            handles = gm_page.locator('#me-overlay circle[fill="#ffd24a"]')
            assert handles.count() >= 2, handles.count()
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights", json={"lights": []})
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": saved_walls})


def test_toggle_off_no_drag(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights", json={"lights": [
            {"id": "sm-l2", "x": 490, "y": 490, "bright_ft": 20, "dim_ft": 20,
             "color": "#ffb347", "color2": "#ff7a1a", "type": "torch"}]})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(400)

            # Turn the toggle off.
            gm_page.click("#me-selmove-btn")
            assert gm_page.get_attribute("#me-selmove-btn", "aria-pressed") == "false"

            b0 = _lights(c, mid)[0]
            light = gm_page.locator(".me-light").first
            light.dblclick()   # still selects for toolbar, but not draggable
            gm_page.wait_for_timeout(150)
            bb = light.bounding_box()
            hx, hy = bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2
            gm_page.mouse.move(hx, hy)
            gm_page.mouse.down()
            gm_page.mouse.move(hx + 160, hy + 120, steps=10)
            gm_page.mouse.up()
            gm_page.wait_for_timeout(300)
            b1 = _lights(c, mid)[0]
            assert (b1["x"], b1["y"]) == (b0["x"], b0["y"]), (b0, b1)
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights", json={"lights": []})
