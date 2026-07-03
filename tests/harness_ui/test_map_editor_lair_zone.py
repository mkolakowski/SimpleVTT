"""v2.870.0 — the map editor's Lair Zone tool.

The 🎯 Lair Zone tool places areas (like terrain) that carry a label + a list
of the lair-action ids they target. Drag a rectangle, or use ⬡ Free polygon to
click vertices and close on the first. New zones pick up the label + actions
from the toolbar inputs. Saved via `PUT /map/{id}/lair_zones`.
"""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def _zones(c, mid):
    return c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lair_zones").json()["lair_zones"]


def _prime_pointer(page, cx, cy):
    """The very first pointerdown on a freshly-loaded editor stage can be
    dropped by the browser; a neutral click (no tool active) absorbs it so the
    real placement drag registers."""
    page.mouse.move(cx, cy)
    page.mouse.down()
    page.mouse.up()
    page.wait_for_timeout(120)


def test_lair_zone_rect_placement_with_actions(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lair_zones", json={"lair_zones": []})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(400)

            box = gm_page.locator("#me-overlay").bounding_box()
            cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] * 0.6
            _prime_pointer(gm_page, cx, cy)

            gm_page.click("#me-lairzone-btn")
            assert gm_page.get_attribute("#me-lairzone-btn", "aria-pressed") == "true"
            gm_page.fill("#me-lairzone-label", "Magma vent")
            gm_page.fill("#me-lairzone-actions", "magma-erupts, tremor")

            # Drag a rectangle over the stage's lower half.
            gm_page.mouse.move(cx - 110, cy - 60)
            gm_page.mouse.down()
            gm_page.mouse.move(cx + 110, cy + 60, steps=6)
            gm_page.mouse.up()
            gm_page.wait_for_timeout(500)

            lz = _zones(c, mid)
            assert len(lz) == 1, lz
            assert lz[0]["label"] == "Magma vent", lz[0]
            assert lz[0]["actions"] == ["magma-erupts", "tremor"], lz[0]
            assert lz[0]["w"] > 6 and lz[0]["h"] > 6, lz[0]
            # Renders as a .me-lairzone element in the editor.
            expect(gm_page.locator(".me-lairzone")).to_have_count(1)
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lair_zones",
                  json={"lair_zones": []})


def test_lair_zone_free_polygon_placement(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lair_zones", json={"lair_zones": []})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(400)

            box = gm_page.locator("#me-overlay").bounding_box()
            cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] * 0.55
            _prime_pointer(gm_page, cx, cy)

            # Free-polygon toggle also flips into lair-zone mode.
            gm_page.click("#me-lairzone-poly-btn")
            assert gm_page.get_attribute("#me-lairzone-poly-btn", "aria-pressed") == "true"

            pts = [(-120, -70), (120, -70), (150, 60), (0, 120), (-150, 60)]
            for dx, dy in pts:
                gm_page.mouse.click(cx + dx, cy + dy)
                gm_page.wait_for_timeout(110)
            gm_page.mouse.click(cx + pts[0][0], cy + pts[0][1])  # close on first
            gm_page.wait_for_timeout(500)

            lz = _zones(c, mid)
            assert len(lz) == 1, lz
            assert len(lz[0].get("points") or []) == 5, lz[0]
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lair_zones",
                  json={"lair_zones": []})
