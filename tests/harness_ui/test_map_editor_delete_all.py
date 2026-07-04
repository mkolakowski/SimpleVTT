"""v2.895.0 — the map editor's "Delete all" button.

Wipes every placed element on the map, gated behind a confirmation that makes
you type DELETE. Undoable (snapshots history first).
"""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def test_delete_all_requires_typing_DELETE_then_clears(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        # Seed a couple of layers so there's something to delete.
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": [
            {"id": "w", "x1": 100, "y1": 100, "x2": 260, "y2": 100, "style": "stone"}]})
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/terrain", json={"terrain": [
            {"id": "t", "x": 300, "y": 300, "w": 80, "h": 80, "type": "water"}]})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(400)

            gm_page.locator("#me-delete-all-btn").click()
            dlg = gm_page.locator('[role="dialog"][aria-label="Delete all map elements"]')
            expect(dlg).to_be_visible()

            del_btn = dlg.locator("button", has_text="Delete everything")
            # Disabled until the exact word DELETE is typed.
            assert del_btn.is_disabled(), "confirm button should start disabled"
            dlg.locator("input").fill("delete")  # wrong case
            assert del_btn.is_disabled(), "lowercase 'delete' must not enable it"
            dlg.locator("input").fill("DELETE")
            expect(del_btn).to_be_enabled()
            del_btn.click()
            gm_page.wait_for_timeout(600)

            # Every seeded layer is now empty server-side.
            walls = c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls").json()["walls"]
            terrain = c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/terrain").json()["terrain"]
            assert walls == [], walls
            assert terrain == [], terrain
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/terrain", json={"terrain": []})


def test_delete_all_cancel_keeps_elements(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": [
            {"id": "w", "x1": 100, "y1": 100, "x2": 260, "y2": 100, "style": "stone"}]})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(400)
            gm_page.locator("#me-delete-all-btn").click()
            dlg = gm_page.locator('[role="dialog"][aria-label="Delete all map elements"]')
            expect(dlg).to_be_visible()
            dlg.locator("button", has_text="Cancel").click()
            expect(dlg).to_have_count(0)
            gm_page.wait_for_timeout(200)
            walls = c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls").json()["walls"]
            assert len(walls) == 1, walls  # untouched
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})
