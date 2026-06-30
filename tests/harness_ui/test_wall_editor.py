"""v2.768.0 — tabletop wall/door rendering (editing moved to the map editor).

The tabletop no longer carries wall/hotspot edit toggles — authoring lives in
the dedicated map editor (`/campaign/{cid}/map/{id}/edit`). The tabletop still
*renders* the wall/door overlay (kept live by `walls_update`); this test
verifies that, and that the edit toggles are gone in favour of an ✏ Edit-map
link.
"""
from __future__ import annotations

from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def test_tabletop_renders_walls_no_edit_toggle(gm_page: Page) -> None:
    errors: list[str] = []
    gm_page.on("pageerror", lambda e: errors.append(str(e)))
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
    gm_page.wait_for_function(
        "() => document.getElementById('wall-overlay') && "
        "typeof window._onWallsUpdate === 'function'", timeout=8000)

    # The in-canvas wall/hotspot EDIT toggles are gone (editing → map editor).
    assert gm_page.locator("#wall-edit-btn").count() == 0
    assert gm_page.locator("#hotspot-edit-btn").count() == 0
    # …replaced by a quick link to the dedicated editor.
    expect(gm_page.locator('.canvas-tools a', has_text="Edit map")).to_be_visible()

    # The overlay still renders walls + doors pushed over the WS.
    gm_page.evaluate("""() => window._onWallsUpdate({ walls: [
        { id: 'a', x1: 10, y1: 10, x2: 200, y2: 10, door: false, open: false },
        { id: 'b', x1: 200, y1: 10, x2: 200, y2: 200, door: true, open: false }
    ]})""")
    lines = gm_page.locator("#wall-overlay line")
    assert lines.count() == 4, lines.count()  # 2 visible + 2 hit
    dashed = gm_page.eval_on_selector_all(
        "#wall-overlay line",
        "els => els.filter(e => e.getAttribute('stroke-dasharray')).length")
    assert dashed >= 1  # the door is dashed

    assert not errors, f"JS errors: {errors}"
