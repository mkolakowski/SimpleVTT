"""v2.765.0 — placing a light source in the map editor.

Enters light mode, sets the bright/dim radius fields, clicks the map, and
asserts a light persists server-side with the chosen radii + a ring renders.
(Preset types are covered by ``test_map_light_types.py``.)
"""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID, me_clear_toolbar


def test_editor_places_light(gm_page: Page) -> None:
    errors: list[str] = []
    gm_page.on("pageerror", lambda e: errors.append(str(e)))
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights", json={"lights": []})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            overlay = gm_page.locator("#me-overlay")
            expect(overlay).to_be_visible()
            me_clear_toolbar(gm_page)  # map is full-bleed behind the toolbar
            gm_page.locator("#me-light-btn").click()
            # v2.784.0 — radii are their own fields now.
            gm_page.fill("#me-light-bright", "25")
            gm_page.fill("#me-light-dim", "50")
            box = overlay.bounding_box()
            gm_page.mouse.click(box["x"] + 120, box["y"] + 120)
            gm_page.wait_for_timeout(400)

            lights = c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights").json()["lights"]
            assert len(lights) == 1, lights
            assert lights[0]["bright_ft"] == 25.0
            assert lights[0]["dim_ft"] == 50.0
            # A light marker rendered on the overlay.
            assert gm_page.locator("#me-overlay .me-light").count() == 1
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights", json={"lights": []})

    assert not errors, f"JS errors: {errors}"


def test_editor_light_flicker_speed(gm_page: Page) -> None:
    """v2.935.0 — the flicker-speed dropdown sets a new light's flicker rate."""
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights", json={"lights": []})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            me_clear_toolbar(gm_page)
            gm_page.locator("#me-light-btn").click()
            gm_page.select_option("#me-light-flicker", "2")  # ⚡ fast
            box = gm_page.locator("#me-overlay").bounding_box()
            gm_page.mouse.click(box["x"] + 140, box["y"] + 140)
            gm_page.wait_for_timeout(400)
            lights = c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights").json()["lights"]
            assert len(lights) == 1, lights
            assert lights[0]["flicker"] == 2.0, lights[0]
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights", json={"lights": []})
