"""v2.850.0 — double-click-select a light; the Markers controls edit it.

Double-clicking a placed light selects it: the toolbar type select, flicker
colour pickers, and B/D radius fields mirror its values; editing a field
live-updates the saved light and flips its type to ``custom`` (unless the
values still match a preset). The right-click 🎨 pop-out edits the colour
pair directly. Esc deselects.
"""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def _lights(c, mid):
    return c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights").json()["lights"]


def test_dblclick_select_edits_light(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights", json={"lights": [
            {"id": "sel1", "x": 500, "y": 500, "bright_ft": 20, "dim_ft": 20,
             "color": "#ffb347", "color2": "#ff7a1a", "type": "torch"},
        ]})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(400)

            # Double-click the light → toolbar mirrors its values.
            gm_page.locator(".me-light").first.dispatch_event("dblclick")
            gm_page.wait_for_timeout(200)
            vals = gm_page.evaluate("""() => ({
                type: document.getElementById('me-light-type').value,
                b: document.getElementById('me-light-bright').value,
                d: document.getElementById('me-light-dim').value,
                c1: document.getElementById('me-light-c1').value,
                c2: document.getElementById('me-light-c2').value,
                cap: document.getElementById('me-light-sel-cap').textContent,
            })""")
            assert vals["type"] == "torch", vals
            assert vals["b"] == "20" and vals["d"] == "20", vals
            assert vals["c1"] == "#ffb347" and vals["c2"] == "#ff7a1a", vals
            assert "selected" in vals["cap"], vals

            # Edit the bright radius → the saved light updates + flips to custom.
            gm_page.fill("#me-light-bright", "35")
            gm_page.dispatch_event("#me-light-bright", "change")
            gm_page.wait_for_timeout(400)
            ls = _lights(c, mid)
            assert ls[0]["bright_ft"] == 35.0, ls
            assert ls[0]["type"] == "custom", ls

            # Edit colour 2 via the toolbar picker → persists.
            gm_page.evaluate("""() => {
                const el = document.getElementById('me-light-c2');
                el.value = '#00ff88';
                el.dispatchEvent(new Event('change', { bubbles: true }));
            }""")
            gm_page.wait_for_timeout(400)
            assert _lights(c, mid)[0]["color2"] == "#00ff88"

            # Esc deselects (caption reverts).
            gm_page.keyboard.press("Escape")
            gm_page.wait_for_timeout(150)
            cap = gm_page.evaluate(
                "() => document.getElementById('me-light-sel-cap').textContent")
            assert "selected" not in cap, cap
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights", json={"lights": []})


def test_rightclick_colour_popout(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights", json={"lights": [
            {"id": "pop1", "x": 480, "y": 480, "bright_ft": 30, "dim_ft": 30,
             "color": "#ffd27f", "color2": "#ffb347", "type": "lantern"},
        ]})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(400)

            gm_page.locator(".me-light").first.dispatch_event("contextmenu")
            fly_btn = gm_page.locator("#me-ctx-menu button", has_text="Flicker colours")
            expect(fly_btn).to_be_visible()
            fly_btn.dispatch_event("mouseenter")   # opens the pop-out
            gm_page.wait_for_timeout(150)

            # Change colour 2 in the pop-out → persists + type flips to custom.
            gm_page.evaluate("""() => {
                const el = document.querySelector('.me-ctx-fly .me-light-fly-color2');
                el.value = '#3366ff';
                el.dispatchEvent(new Event('change', { bubbles: true }));
            }""")
            gm_page.wait_for_timeout(400)
            ls = _lights(c, mid)
            assert ls[0]["color2"] == "#3366ff", ls
            assert ls[0]["type"] == "custom", ls
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights", json={"lights": []})
