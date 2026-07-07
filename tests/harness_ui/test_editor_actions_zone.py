"""v2.932.0 — View sits beside Tools in the Actions zone. v2.939.0 — the Actions
zone (File · Tools · View) is shown/hidden by its far-left toggle button."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def test_actions_zone_button_hides_file_tools_view(gm_page: Page) -> None:
    gm_page.set_viewport_size({"width": 1800, "height": 1000})
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
    expect(gm_page.locator("#me-overlay")).to_be_visible()
    gm_page.wait_for_timeout(400)
    gm_page.evaluate("(mid) => localStorage.removeItem('me-zones-hidden-' + mid)", mid)
    gm_page.reload()
    expect(gm_page.locator("#me-overlay")).to_be_visible()
    gm_page.wait_for_timeout(400)

    # The zone toggle buttons sit left of every group.
    btn_x = gm_page.locator('.me-zone-toggle[data-zone="Actions"]').bounding_box()["x"]
    file_x = gm_page.locator('.me-group[aria-label="File"]').bounding_box()["x"]
    assert btn_x < file_x, (btn_x, file_x)

    for label in ("File", "Tools", "View"):
        expect(gm_page.locator(f'.me-group[aria-label="{label}"]')).to_be_visible()

    # Click the "Actions" zone button → File · Tools · View all hide.
    gm_page.locator('.me-zone-toggle[data-zone="Actions"]').click()
    gm_page.wait_for_timeout(200)
    for label in ("File", "Tools", "View"):
        expect(gm_page.locator(f'.me-group[aria-label="{label}"]')).to_be_hidden()
