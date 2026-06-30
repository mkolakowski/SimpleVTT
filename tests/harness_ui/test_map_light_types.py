"""v2.778.0 — light-source presets in the map editor.

The toolbar light-type select drives placement, and a placed light's
right-click menu can switch it to any preset. Lights persist (incl. the
`type` tag), so this asserts via the lights API.
"""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def _lights(c, mid):
    return c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights").json()["lights"]


def _open_editor(gm_page, mid):
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
    expect(gm_page.locator("#me-overlay")).to_be_visible()
    gm_page.wait_for_timeout(400)


def test_place_light_with_preset(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights", json={"lights": []})
        try:
            _open_editor(gm_page, mid)
            gm_page.locator("#me-light-btn").click()           # enter light mode
            gm_page.select_option("#me-light-type", "daylight")
            ov = gm_page.locator("#me-overlay").bounding_box()
            gm_page.mouse.click(ov["x"] + ov["width"] / 2, ov["y"] + ov["height"] / 2)
            gm_page.wait_for_timeout(350)
            ls = _lights(c, mid)
            assert len(ls) == 1, ls
            assert ls[0]["bright_ft"] == 60.0 and ls[0]["dim_ft"] == 60.0, ls
            assert ls[0]["type"] == "daylight", ls
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights", json={"lights": []})


def test_light_marker_flicker_matches_type(gm_page: Page) -> None:
    # v2.784.1 — the marker has a larger hit target + a per-type flicker
    # animation; changing the type changes the flicker.
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights", json={"lights": [
            {"id": "l1", "x": 300, "y": 300, "bright_ft": 20, "dim_ft": 20,
             "color": "#ffb347", "type": "torch"}]})
        try:
            _open_editor(gm_page, mid)
            # Larger right-click target.
            hit = gm_page.locator("#me-overlay circle.me-light").first
            assert float(hit.get_attribute("r")) >= 24, hit.get_attribute("r")
            # Torch flicker speed.
            assert gm_page.locator("#me-overlay animate").first.get_attribute("dur") == "0.7s"
            # Re-type to Candle → faster flicker.
            box = hit.bounding_box()
            gm_page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2,
                                button="right")
            gm_page.locator("#me-ctx-menu button", has_text="Candle").click()
            gm_page.wait_for_timeout(300)
            assert gm_page.locator("#me-overlay animate").first.get_attribute("dur") == "0.45s"
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights", json={"lights": []})


def test_right_click_changes_light_type(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights", json={"lights": [
            {"id": "l1", "x": 300, "y": 300, "bright_ft": 5, "dim_ft": 5,
             "color": "#ffcf8a", "type": "candle"}]})
        try:
            _open_editor(gm_page, mid)
            dot = gm_page.locator("#me-overlay circle.me-light").first
            box = dot.bounding_box()
            gm_page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2,
                                button="right")
            gm_page.locator("#me-ctx-menu button", has_text="Daylight").click()
            gm_page.wait_for_timeout(350)
            ls = _lights(c, mid)
            assert ls[0]["type"] == "daylight", ls
            assert ls[0]["bright_ft"] == 60.0 and ls[0]["dim_ft"] == 60.0, ls
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights", json={"lights": []})
