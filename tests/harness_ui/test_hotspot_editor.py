"""v2.768.0 — tabletop hotspot rendering + popup (editing moved to the editor).

Hotspot authoring lives in the dedicated map editor now; the tabletop renders
the markers and shows the description popup when a player clicks one. This
verifies the render + popup, and that the edit toggle is gone.
"""
from __future__ import annotations

from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def test_hotspot_render_and_popup(gm_page: Page) -> None:
    errors: list[str] = []
    gm_page.on("pageerror", lambda e: errors.append(str(e)))
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
    gm_page.wait_for_function(
        "() => document.getElementById('wall-overlay') && "
        "typeof window._onHotspotsUpdate === 'function'", timeout=8000)

    # The in-canvas hotspot edit toggle is gone (authoring → map editor).
    assert gm_page.locator("#hotspot-edit-btn").count() == 0

    # A hotspot pushed over the WS renders; clicking it opens its popup.
    gm_page.evaluate("""() => window._onHotspotsUpdate({ hotspots: [
        { id: 'h1', x: 120, y: 140, label: 'Altar', description: 'A bloodied altar.' }
    ]})""")
    marker = gm_page.locator(".map-hotspot")
    assert marker.count() == 1, marker.count()
    marker.first.click()
    popup = gm_page.locator("#hotspot-popup")
    expect(popup).to_be_visible()
    expect(popup).to_contain_text("Altar")
    expect(popup).to_contain_text("bloodied altar")

    # A roll-prompt hotspot shows the 🎲 Roll button.
    gm_page.locator("#hotspot-popup button", has_text="Close").click()
    gm_page.evaluate("""() => window._onHotspotsUpdate({ hotspots: [
        { id: 'h2', x: 200, y: 200, label: 'Trap', description: 'Spikes!', roll: '2d6' }
    ]})""")
    gm_page.locator(".map-hotspot").first.click()
    expect(
        gm_page.locator("#hotspot-popup button", has_text="Roll 2d6")
    ).to_be_visible()

    assert not errors, f"JS errors: {errors}"
