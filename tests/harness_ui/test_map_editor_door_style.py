"""v2.772.0 — map editor: dedicated 🚪 Door button + wall/door style picker.

v2.902.0 — a door is EMBEDDED in a wall: in Door mode you click a wall and a
door opening is appended to its ``doors`` list — the wall stays ONE object (no
split). Multiple doors on the same wall snap flush together.
"""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID, me_clear_toolbar


def _place_door_at(gm_page: Page, frac: float, wall_box) -> None:
    """Click along the seeded horizontal wall at fraction ``frac`` of its span."""
    gm_page.mouse.click(wall_box["x"] + wall_box["width"] * frac,
                        wall_box["y"] + wall_box["height"] / 2)
    gm_page.wait_for_timeout(300)


def test_place_door_embeds_in_wall_without_splitting(gm_page: Page) -> None:
    errors: list[str] = []
    gm_page.on("pageerror", lambda e: errors.append(str(e)))
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": [
            {"id": "w", "x1": 200, "y1": 300, "x2": 800, "y2": 300, "style": "wood"}]})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(300)
            me_clear_toolbar(gm_page)

            gm_page.locator("#me-door-btn").click()
            box = gm_page.locator('#me-overlay line[stroke="transparent"]').first.bounding_box()
            _place_door_at(gm_page, 0.5, box)

            walls = c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls").json()["walls"]
            # Still ONE wall — not split — carrying one embedded door.
            assert len(walls) == 1, walls
            w = walls[0]
            assert w["id"] == "w" and w["style"] == "wood", w
            assert len(w.get("doors", [])) == 1, w
            d = w["doors"][0]
            assert 0 <= d["t0"] < d["t1"] <= 1, d
            # The embedded door renders a knob glyph.
            assert gm_page.locator("#me-overlay circle").count() >= 1
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})

    assert not errors, f"JS errors: {errors}"


def test_two_doors_on_one_wall_snap_flush(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        # A long wall so a one-cell door is a small fraction (doors placed close
        # together snap so their edges touch).
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": [
            {"id": "w", "x1": 100, "y1": 300, "x2": 900, "y2": 300, "style": "stone"}]})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(300)
            me_clear_toolbar(gm_page)
            gm_page.locator("#me-door-btn").click()
            box = gm_page.locator('#me-overlay line[stroke="transparent"]').first.bounding_box()
            _place_door_at(gm_page, 0.48, box)
            _place_door_at(gm_page, 0.55, box)  # close to the first → snaps flush

            walls = c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls").json()["walls"]
            assert len(walls) == 1, walls
            doors = sorted(walls[0].get("doors", []), key=lambda d: d["t0"])
            assert len(doors) == 2, doors
            # The second door's near edge snapped to the first's far edge.
            assert abs(doors[1]["t0"] - doors[0]["t1"]) < 0.01, doors
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})


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
