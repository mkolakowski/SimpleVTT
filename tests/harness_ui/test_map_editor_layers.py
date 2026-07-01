"""v2.790.3 — per-layer visibility toggles in the map editor."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def test_layer_toggle_hides_walls(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": [
            {"id": "w", "x1": 150, "y1": 150, "x2": 320, "y2": 150, "style": "stone"}]})
        try:
            editor = f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit"
            gm_page.goto(editor)
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(400)
            assert gm_page.locator('#me-overlay line[stroke="transparent"]').count() >= 1
            # Hide the Walls layer → the wall (and its hit-line) disappears.
            gm_page.uncheck("#me-layer-walls")
            gm_page.wait_for_timeout(200)
            assert gm_page.locator('#me-overlay line[stroke="transparent"]').count() == 0
            # Persists across reload (localStorage).
            gm_page.reload()
            gm_page.wait_for_timeout(500)
            assert gm_page.is_checked("#me-layer-walls") is False
            assert gm_page.locator('#me-overlay line[stroke="transparent"]').count() == 0
            # Re-show it.
            gm_page.check("#me-layer-walls")
            gm_page.wait_for_timeout(200)
            assert gm_page.locator('#me-overlay line[stroke="transparent"]').count() >= 1
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})


_LAYER_IDS = [
    "#me-layer-walls", "#me-layer-terrain", "#me-layer-lights", "#me-layer-hotspots",
    "#me-layer-fog", "#me-layer-gmpins", "#me-layer-props", "#me-layer-labels",
    "#me-layer-tokens",
]


def test_layers_all_none_toggle(gm_page: Page) -> None:
    """v2.818.0 — the Layers "All / None" button flips every overlay at once."""
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
    expect(gm_page.locator("#me-overlay")).to_be_visible()
    gm_page.wait_for_timeout(300)

    toggle = gm_page.locator("#me-layers-toggle")
    expect(toggle).to_be_visible()

    # Every layer checkbox starts checked (all overlays shown).
    for sel in _LAYER_IDS:
        assert gm_page.locator(sel).is_checked(), sel
    # One click hides every overlay — all boxes unchecked.
    toggle.click()
    gm_page.wait_for_timeout(120)
    for sel in _LAYER_IDS:
        assert gm_page.locator(sel).is_checked() is False, sel
    # A second click restores them all.
    toggle.click()
    gm_page.wait_for_timeout(120)
    for sel in _LAYER_IDS:
        assert gm_page.locator(sel).is_checked(), sel
