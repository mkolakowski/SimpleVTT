"""v2.754.0 — Maps 2.0 GM wall-editor overlay.

Drives the real `#wall-overlay` SVG + the GM "🧱 Walls" toggle: entering edit
mode flips aria-pressed, reveals the door checkbox, and makes the overlay
interactive; a `walls_update` (via `window._onWallsUpdate`) renders wall + door
segments as SVG lines.
"""
from __future__ import annotations

from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def test_wall_editor_toggle_and_render(gm_page: Page) -> None:
    errors: list[str] = []
    gm_page.on("pageerror", lambda e: errors.append(str(e)))
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
    gm_page.wait_for_function(
        "() => document.getElementById('wall-overlay') && "
        "typeof window._onWallsUpdate === 'function'", timeout=8000)

    btn = gm_page.locator("#wall-edit-btn")
    expect(btn).to_be_visible()
    assert btn.get_attribute("aria-pressed") == "false"

    # Enter edit mode: aria-pressed flips, the door checkbox appears.
    btn.click()
    assert btn.get_attribute("aria-pressed") == "true"
    expect(gm_page.locator("#wall-door-toggle")).to_be_visible()
    assert gm_page.eval_on_selector(
        "#wall-overlay", "el => el.style.pointerEvents") == "auto"

    # Render a wall + a door via the WS hook.
    gm_page.evaluate("""() => window._onWallsUpdate({ walls: [
        { id: 'a', x1: 10, y1: 10, x2: 200, y2: 10, door: false, open: false },
        { id: 'b', x1: 200, y1: 10, x2: 200, y2: 200, door: true, open: false }
    ]})""")
    # Two segments → two visible lines + two hit lines = 4 <line> nodes.
    # (_onWallsUpdate renders synchronously, so the nodes exist immediately.)
    lines = gm_page.locator("#wall-overlay line")
    assert lines.count() == 4, lines.count()
    # The door's visible line is dashed.
    dashed = gm_page.eval_on_selector_all(
        "#wall-overlay line",
        "els => els.filter(e => e.getAttribute('stroke-dasharray')).length")
    assert dashed >= 1

    # Leaving edit mode hides the door toggle + locks the overlay.
    btn.click()
    assert btn.get_attribute("aria-pressed") == "false"
    expect(gm_page.locator("#wall-door-toggle")).to_be_hidden()

    assert not errors, f"JS errors: {errors}"
