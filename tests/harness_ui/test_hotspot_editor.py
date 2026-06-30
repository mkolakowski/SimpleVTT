"""v2.756.0 — Maps 2.0 clickable hotspots overlay.

Drives the `#wall-overlay` hotspot markers + the GM "📍 Spots" toggle: a
`hotspots_update` (via `window._onHotspotsUpdate`) renders `.map-hotspot`
markers, and clicking one in play mode opens the `#hotspot-popup` with its
label + description.
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

    # The GM toggle exists.
    spot_btn = gm_page.locator("#hotspot-edit-btn")
    expect(spot_btn).to_be_visible()

    # Render a hotspot via the WS hook (play mode → click opens the popup).
    gm_page.evaluate("""() => window._onHotspotsUpdate({ hotspots: [
        { id: 'h1', x: 120, y: 140, label: 'Altar', description: 'A bloodied altar.' }
    ]})""")
    marker = gm_page.locator(".map-hotspot")
    assert marker.count() == 1, marker.count()

    # Click the marker → the description popup appears with the label + text.
    marker.first.click()
    popup = gm_page.locator("#hotspot-popup")
    expect(popup).to_be_visible()
    expect(popup).to_contain_text("Altar")
    expect(popup).to_contain_text("bloodied altar")

    # Closing the popup removes it.
    gm_page.locator("#hotspot-popup button", has_text="Close").click()
    expect(gm_page.locator("#hotspot-popup")).to_have_count(0)

    # The 📍 toggle arms spot-edit mode.
    spot_btn.click()
    assert spot_btn.get_attribute("aria-pressed") == "true"

    assert not errors, f"JS errors: {errors}"
