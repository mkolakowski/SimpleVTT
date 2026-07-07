"""v2.939.0 — the far-left zone toggle buttons hide a whole zone (incl. Lair);
per-group collapse (clicking a group's own label) still folds it to a vertical
slim strip.
"""
from __future__ import annotations

from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID
import httpx


def _open(gm_page: Page):
    gm_page.set_viewport_size({"width": 1800, "height": 1000})
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
    expect(gm_page.locator("#me-overlay")).to_be_visible()
    gm_page.wait_for_timeout(400)
    # Clean slate.
    gm_page.evaluate("(mid) => localStorage.removeItem('me-zones-hidden-' + mid)", mid)
    gm_page.evaluate("(mid) => localStorage.removeItem('me-collapsed-' + mid)", mid)
    gm_page.reload()
    expect(gm_page.locator("#me-overlay")).to_be_visible()
    gm_page.wait_for_timeout(400)
    return mid


def test_draw_zone_button_hides_its_groups_including_lair(gm_page: Page) -> None:
    _open(gm_page)
    lair = gm_page.locator('.me-group[aria-label="Lair zones"]')
    expect(lair).to_be_visible()

    gm_page.locator('.me-zone-toggle[data-zone="Draw"]').click()
    gm_page.wait_for_timeout(200)
    # Lair + every other Draw group hides.
    for label in ("Walls", "Terrain", "Lighting", "Environment", "Lair zones"):
        expect(gm_page.locator(f'.me-group[aria-label="{label}"]')).to_be_hidden()


def test_per_group_collapse_title_is_vertical(gm_page: Page) -> None:
    _open(gm_page)
    walls = gm_page.locator('.me-group[aria-label="Walls"]')
    assert "me-collapsed" not in (walls.get_attribute("class") or "")

    # Click the group's OWN label → it folds to a slim strip whose title is vertical.
    gm_page.locator('.me-group[aria-label="Walls"] .me-grp-lbl').click()
    gm_page.wait_for_timeout(150)
    assert "me-collapsed" in (walls.get_attribute("class") or "")
    wm = gm_page.eval_on_selector(
        '.me-group[aria-label="Walls"].me-collapsed .me-grp-lbl',
        "e => getComputedStyle(e).writingMode")
    assert wm.startswith("vertical"), wm
