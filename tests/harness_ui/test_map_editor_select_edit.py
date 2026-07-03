"""v2.851.0 — select-to-edit for walls (material) + terrain (type).

Double-clicking a wall segment selects it: `#me-wall-style` mirrors its
material and changing the select persists to the wall. Same for terrain
regions via `#me-terrain-type`. Esc deselects (further changes don't touch
the previously selected object).
"""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def test_dblclick_wall_material_edit(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        saved_walls = c.get(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls").json()["walls"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": [
            {"id": "selw", "x1": 400, "y1": 400, "x2": 700, "y2": 400, "style": "wood"},
        ]})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(400)

            # Double-click the wall's hit line → the material select mirrors it.
            gm_page.locator("#me-overlay line[stroke='transparent']").first.dispatch_event("dblclick")
            gm_page.wait_for_timeout(200)
            assert gm_page.evaluate(
                "() => document.getElementById('me-wall-style').value") == "wood"

            # Change the material → persists to the selected wall.
            gm_page.select_option("#me-wall-style", "brick")
            gm_page.wait_for_timeout(400)
            ws = c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls").json()["walls"]
            assert ws[0]["style"] == "brick", ws

            # Esc deselects — further select changes leave the wall alone.
            gm_page.keyboard.press("Escape")
            gm_page.select_option("#me-wall-style", "cave")
            gm_page.wait_for_timeout(300)
            ws = c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls").json()["walls"]
            assert ws[0]["style"] == "brick", ws
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls",
                  json={"walls": saved_walls})


def test_dblclick_terrain_type_edit(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/terrain", json={"terrain": [
            {"id": "selt", "x": 300, "y": 300, "w": 300, "h": 220, "type": "water"},
        ]})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(400)

            gm_page.locator(".me-terrain").first.dispatch_event("dblclick")
            gm_page.wait_for_timeout(200)
            assert gm_page.evaluate(
                "() => document.getElementById('me-terrain-type').value") == "water"

            gm_page.select_option("#me-terrain-type", "swamp")
            gm_page.wait_for_timeout(400)
            ts = c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/terrain").json()["terrain"]
            assert ts[0]["type"] == "swamp", ts
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/terrain", json={"terrain": []})
