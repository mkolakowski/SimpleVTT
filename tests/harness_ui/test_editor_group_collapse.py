"""v2.912.0 — collapsing the Draw zone also collapses the Lair group, and a
collapsed group's title reads vertically (a slim strip that saves toolbar space).
"""
from __future__ import annotations

from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID
import httpx


def test_draw_zone_collapse_includes_lair_and_label_is_vertical(gm_page: Page) -> None:
    gm_page.set_viewport_size({"width": 1800, "height": 1000})
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
    expect(gm_page.locator("#me-overlay")).to_be_visible()
    gm_page.wait_for_timeout(400)

    lair = gm_page.locator('.me-group[aria-label="Lair zones"]')
    # Not collapsed initially.
    assert "me-collapsed" not in (lair.get_attribute("class") or "")

    # Click the "Draw" zone divider label → collapse the whole Draw zone.
    gm_page.locator(".me-zone-lbl", has_text="Draw").click()
    gm_page.wait_for_timeout(200)

    # The Lair group collapsed along with the other Draw-zone groups.
    assert "me-collapsed" in (lair.get_attribute("class") or ""), lair.get_attribute("class")
    for label in ("Walls", "Markers", "Environment", "Tokens"):
        g = gm_page.locator(f'.me-group[aria-label="{label}"]')
        assert "me-collapsed" in (g.get_attribute("class") or ""), label

    # A collapsed group's title reads vertically.
    wm = gm_page.eval_on_selector(
        '.me-group.me-collapsed .me-grp-lbl',
        "e => getComputedStyle(e).writingMode")
    assert wm.startswith("vertical"), wm


def test_zone_collapse_persists_across_reload(gm_page: Page) -> None:
    # v2.912.1 — a zone collapse is written to the per-map `me-collapsed-<MID>`
    # localStorage store (shared with per-group collapse), so it survives a
    # reload. Regression guard: refactoring the zone handler must keep persisting.
    gm_page.set_viewport_size({"width": 1800, "height": 1000})
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
    url = f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit"
    gm_page.goto(url)
    expect(gm_page.locator("#me-overlay")).to_be_visible()
    gm_page.wait_for_timeout(400)

    gm_page.locator(".me-zone-lbl", has_text="Draw").click()
    gm_page.wait_for_timeout(200)
    lair = gm_page.locator('.me-group[aria-label="Lair zones"]')
    assert "me-collapsed" in (lair.get_attribute("class") or "")

    # Reload — the collapsed state was persisted, so it comes back collapsed.
    gm_page.reload()
    expect(gm_page.locator("#me-overlay")).to_be_visible()
    gm_page.wait_for_timeout(400)
    for label in ("Walls", "Markers", "Environment", "Lair zones", "Tokens"):
        g = gm_page.locator(f'.me-group[aria-label="{label}"]')
        assert "me-collapsed" in (g.get_attribute("class") or ""), f"{label} not persisted"
