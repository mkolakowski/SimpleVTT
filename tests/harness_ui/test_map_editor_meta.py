"""v2.786.2 — inline map rename (header ✎) + a Tags group in the editor."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def _mid(c):
    return c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]


def test_rename_map_from_header(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = _mid(c)
        editor = f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit"
        gm_page.goto(editor)
        original = gm_page.locator("#me-map-name").inner_text()
        try:
            gm_page.locator("#me-rename-btn").click()
            gm_page.fill("#me-map-name-input", "Renamed Test Map")
            gm_page.locator("#me-rename-save").click()
            expect(gm_page.locator("#me-map-name")).to_have_text("Renamed Test Map")
            # Persisted: reload shows the new name.
            gm_page.goto(editor)
            expect(gm_page.locator("#me-map-name")).to_have_text("Renamed Test Map")
        finally:
            c.post(f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/rename",
                   json={"name": original})


def test_map_tags_group(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = _mid(c)
        editor = f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit"
        try:
            gm_page.goto(editor)
            gm_page.fill("#me-tags-input", "alpha, beta")
            gm_page.locator("#me-tags-save").click()
            gm_page.wait_for_timeout(300)
            # Persisted: reload shows the tags.
            gm_page.goto(editor)
            val = gm_page.locator("#me-tags-input").input_value()
            assert "alpha" in val and "beta" in val, val
        finally:
            c.post(f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/tags", json={"tags": []})
