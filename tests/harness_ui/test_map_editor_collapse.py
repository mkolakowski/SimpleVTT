"""v2.811.0 — collapsible map-editor toolbar groups."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def test_group_collapses_and_persists(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
    editor = f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit"
    gm_page.goto(editor)
    expect(gm_page.locator("#me-overlay")).to_be_visible()
    gm_page.wait_for_timeout(300)
    grid_label = gm_page.locator('.me-group[aria-label="Grid"] .me-grp-lbl')

    # Grid controls start visible.
    assert gm_page.locator("#me-grid-type").is_visible()
    # Click the Grid label → the group collapses (controls hidden).
    grid_label.click()
    gm_page.wait_for_timeout(150)
    assert gm_page.locator("#me-grid-type").is_visible() is False
    # Persists across reload (localStorage).
    gm_page.reload()
    gm_page.wait_for_timeout(400)
    assert gm_page.locator("#me-grid-type").is_visible() is False
    # Clicking again re-expands it.
    gm_page.locator('.me-group[aria-label="Grid"] .me-grp-lbl').click()
    gm_page.wait_for_timeout(150)
    assert gm_page.locator("#me-grid-type").is_visible()


def test_zone_button_toggles_whole_zone(gm_page: Page) -> None:
    """v2.939.0 — the far-left zone toggle buttons show / hide a whole zone; the
    open/closed state is remembered per map, and zones are independent."""
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
    expect(gm_page.locator("#me-overlay")).to_be_visible()
    gm_page.wait_for_timeout(300)
    # Start from a known state (nothing hidden).
    gm_page.evaluate("(mid) => localStorage.removeItem('me-zones-hidden-' + mid)", mid)
    gm_page.reload()
    expect(gm_page.locator("#me-overlay")).to_be_visible()
    gm_page.wait_for_timeout(300)

    draw_groups = ["Walls", "Terrain", "Lighting", "Environment", "Lair zones"]
    draw_btn = gm_page.locator('.me-zone-toggle[data-zone="Draw"]')
    for g in draw_groups:
        expect(gm_page.locator(f'.me-group[aria-label="{g}"]')).to_be_visible()
    assert draw_btn.get_attribute("aria-pressed") == "true"

    # Click the Draw zone button → every Draw group hides (Map untouched).
    draw_btn.click()
    gm_page.wait_for_timeout(150)
    for g in draw_groups:
        expect(gm_page.locator(f'.me-group[aria-label="{g}"]')).to_be_hidden()
    assert draw_btn.get_attribute("aria-pressed") == "false"
    assert gm_page.locator("#me-grid-type").is_visible()  # Map zone still open

    # Persists across reload, then a second click re-opens the zone.
    gm_page.reload()
    gm_page.wait_for_timeout(400)
    expect(gm_page.locator('.me-group[aria-label="Walls"]')).to_be_hidden()
    gm_page.locator('.me-zone-toggle[data-zone="Draw"]').click()
    gm_page.wait_for_timeout(150)
    for g in draw_groups:
        expect(gm_page.locator(f'.me-group[aria-label="{g}"]')).to_be_visible()
