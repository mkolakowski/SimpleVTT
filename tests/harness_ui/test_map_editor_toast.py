"""v2.825.0 — an explicit save shows a transient toast popup."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def test_explicit_save_shows_toast(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
    expect(gm_page.locator("#me-overlay")).to_be_visible()
    gm_page.wait_for_timeout(300)

    # No toast until the user saves.
    assert gm_page.locator(".me-toast.me-toast--show").count() == 0

    # Click the Save button → a toast pops up confirming the save.
    gm_page.locator("#me-save-btn").click()
    toast = gm_page.locator(".me-toast.me-toast--show")
    expect(toast).to_be_visible(timeout=3000)
    assert "saved" in (toast.inner_text() or "").lower()
