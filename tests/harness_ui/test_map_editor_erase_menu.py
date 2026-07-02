"""v2.770.0 — map editor erase toggle + right-click Move/Delete menu.

Tap no longer deletes by default. Instead: an 🗑 Erase toggle (click an object
to delete) and a right-click context menu (Move / Delete) on any object.
"""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def _seed_walls(c, mid, n):
    walls = [{"id": f"w{i}", "x1": 120 + i * 80, "y1": 120,
              "x2": 120 + i * 80, "y2": 360} for i in range(n)]
    c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": walls})


def _wall_count(c, mid):
    return len(c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls").json()["walls"])


def test_erase_toggle_and_context_menu(gm_page: Page) -> None:
    errors: list[str] = []
    gm_page.on("pageerror", lambda e: errors.append(str(e)))
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        _seed_walls(c, mid, 2)
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(500)
            hits = gm_page.locator('#me-overlay line[stroke="transparent"]')
            assert hits.count() == 2

            def click_first(button="left"):
                box = hits.first.bounding_box()
                gm_page.mouse.click(box["x"] + box["width"] / 2,
                                    box["y"] + box["height"] / 2, button=button)

            # A plain left-click on a wall does NOT delete (the old default).
            click_first()
            gm_page.wait_for_timeout(250)
            assert _wall_count(c, mid) == 2

            # Right-click a wall → context menu (Move + Delete); Delete removes it.
            click_first(button="right")
            menu = gm_page.locator("#me-ctx-menu")
            expect(menu).to_be_visible()
            expect(menu.locator("button", has_text="Move")).to_be_visible()
            menu.locator("button", has_text="Delete").click()
            gm_page.wait_for_timeout(300)
            assert _wall_count(c, mid) == 1

            # Erase mode: a left-click now deletes.
            gm_page.locator("#me-erase-btn").click()
            assert gm_page.locator("#me-erase-btn").get_attribute("aria-pressed") == "true"
            click_first()
            gm_page.wait_for_timeout(300)
            assert _wall_count(c, mid) == 0
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})

    assert not errors, f"JS errors: {errors}"
