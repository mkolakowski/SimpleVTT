"""v2.772.0 — map editor: dedicated 🚪 Door button + wall/door style picker.

v2.897.0 — a door must be placed INTO an existing wall: in Door mode you click a
wall and it splits, inserting a door-width opening that inherits the wall's
material. This verifies clicking a seeded wall yields a door=true segment with
the wall's style.
"""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID, me_clear_toolbar


def test_place_door_in_wall(gm_page: Page) -> None:
    errors: list[str] = []
    gm_page.on("pageerror", lambda e: errors.append(str(e)))
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        # Seed a wall for the door to be placed into (style wood → door inherits).
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": [
            {"id": "w", "x1": 200, "y1": 300, "x2": 560, "y2": 300, "style": "wood"}]})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(300)
            me_clear_toolbar(gm_page)  # map is full-bleed behind the toolbar

            door_btn = gm_page.locator("#me-door-btn")
            door_btn.click()
            assert door_btn.get_attribute("aria-pressed") == "true"

            # Click the wall's hit-line → a door is inserted into it.
            box = gm_page.locator('#me-overlay line[stroke="transparent"]').first.bounding_box()
            gm_page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            gm_page.wait_for_timeout(400)

            walls = c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls").json()["walls"]
            doors = [w for w in walls if w.get("door")]
            assert len(doors) == 1, walls
            assert doors[0]["style"] == "wood", doors  # inherited from the wall
            # The wall was split around the opening (door + at least one flank).
            assert len(walls) >= 2, walls
            # The door renders with a knob (circle) in the overlay.
            assert gm_page.locator("#me-overlay circle").count() >= 1
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})

    assert not errors, f"JS errors: {errors}"


def test_door_on_empty_map_is_rejected(gm_page: Page) -> None:
    """A click on empty map in Door mode places nothing (doors need a wall)."""
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(300)
            me_clear_toolbar(gm_page)
            gm_page.locator("#me-door-btn").click()
            ov = gm_page.locator("#me-overlay").bounding_box()
            gm_page.mouse.click(ov["x"] + 120, ov["y"] + 120)
            gm_page.mouse.click(ov["x"] + 240, ov["y"] + 120)
            gm_page.wait_for_timeout(300)
            walls = c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls").json()["walls"]
            assert walls == [], walls  # nothing placed on empty map
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})
