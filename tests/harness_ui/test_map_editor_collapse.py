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


def test_zone_divider_collapses_whole_zone(gm_page: Page) -> None:
    """v2.820.0 — clicking a zone divider label folds every group in that zone."""
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
    expect(gm_page.locator("#me-overlay")).to_be_visible()
    gm_page.wait_for_timeout(300)

    # v2.924.0 — Theme A: Draw zone = Walls · Terrain · Lighting · Fog & Vision ·
    # Weather · Annotations · Lair · Tokens.
    draw_groups = ["Walls", "Terrain", "Lighting", "Environment", "Annotations", "Tokens"]
    for g in draw_groups:
        assert "me-collapsed" not in (
            gm_page.locator(f'.me-group[aria-label="{g}"]').get_attribute("class") or "")

    # Click the "Draw" zone divider label → every Draw group collapses.
    gm_page.locator('.me-zone-sep > .me-zone-lbl', has_text="Draw").click()
    gm_page.wait_for_timeout(150)
    for g in draw_groups:
        assert "me-collapsed" in (
            gm_page.locator(f'.me-group[aria-label="{g}"]').get_attribute("class") or ""), g
    # The Map zone is untouched (Grid still expanded).
    assert gm_page.locator("#me-grid-type").is_visible()

    # Persists across reload, then a second click re-expands the whole zone.
    gm_page.reload()
    gm_page.wait_for_timeout(400)
    assert "me-collapsed" in (
        gm_page.locator('.me-group[aria-label="Walls"]').get_attribute("class") or "")
    gm_page.locator('.me-zone-sep > .me-zone-lbl', has_text="Draw").click()
    gm_page.wait_for_timeout(150)
    for g in draw_groups:
        assert "me-collapsed" not in (
            gm_page.locator(f'.me-group[aria-label="{g}"]').get_attribute("class") or ""), g
