"""v2.932.0 — View sits beside Tools in the Actions zone, and that zone (File ·
Tools · View) is collapsible via its own zone divider, like Draw / Map."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def test_actions_zone_collapses_file_tools_view(gm_page: Page) -> None:
    gm_page.set_viewport_size({"width": 1800, "height": 1000})
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
    expect(gm_page.locator("#me-overlay")).to_be_visible()
    gm_page.wait_for_timeout(400)

    # View is now in the Actions zone (left), before the Draw divider.
    view_x = gm_page.locator('.me-group[aria-label="View"]').bounding_box()["x"]
    draw_x = gm_page.locator('.me-zone-sep .me-zone-lbl', has_text="Draw").bounding_box()["x"]
    assert view_x < draw_x, (view_x, draw_x)

    for label in ("File", "Tools", "View"):
        g = gm_page.locator(f'.me-group[aria-label="{label}"]')
        assert "me-collapsed" not in (g.get_attribute("class") or "")

    # Click the "Actions" zone divider → File · Tools · View all collapse.
    gm_page.locator('.me-zone-sep .me-zone-lbl', has_text="Actions").click()
    gm_page.wait_for_timeout(200)
    for label in ("File", "Tools", "View"):
        g = gm_page.locator(f'.me-group[aria-label="{label}"]')
        assert "me-collapsed" in (g.get_attribute("class") or ""), label
