"""v2.928.0 — the View group's zoom controls stack vertically (Fit · 🔍+ · % ·
🔍−) so the group is a slim column, not a wide zoom row."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def test_view_zoom_buttons_are_stacked(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
    expect(gm_page.locator("#me-overlay")).to_be_visible()
    gm_page.wait_for_timeout(300)

    zi = gm_page.locator("#me-zoom-in").bounding_box()
    zo = gm_page.locator("#me-zoom-out").bounding_box()
    # Stacked vertically: zoom-in sits above zoom-out, at (roughly) the same x.
    assert zo["y"] > zi["y"] + zi["height"] - 2, (zi, zo)
    assert abs(zo["x"] - zi["x"]) < 6, (zi, zo)
