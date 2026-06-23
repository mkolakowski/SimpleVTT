"""v2.583.0 — left-drag on empty map area pans the tabletop map.

Regression net for the "map can't be moved" bug: right-button drag is
intercepted by the native context menu on macOS Safari / some trackpads,
so the map appeared stuck (zoom — a separate wheel path — still worked).
The fix adds left-drag-on-empty-canvas panning (the standard VTT gesture)
in tabletop.js's canvas mousedown/mousemove/mouseup handlers.

These tests assert the #map-transform translate() actually changes after
a left-drag over empty map area, and that the wheel still zooms (so the
fix didn't regress the working path).

GM = gm_page (authenticated GM context on the tabletop).
"""
from playwright.sync_api import Page

from .conftest import BASE_URL, CAMPAIGN_ID


def _open_tabletop(page: Page):
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    resp = page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
    assert resp is not None and resp.ok, "tabletop failed to load"
    page.wait_for_selector("#vtt-canvas", timeout=8000)
    # Let the initial render + any saved-view restore settle.
    page.wait_for_timeout(600)
    return errors


def _transform(page: Page) -> str:
    return page.eval_on_selector("#map-transform", "el => el.style.transform")


def _empty_canvas_point(page: Page):
    """A point near the map-pane top-left corner — far from the center
    where demo tokens cluster — so the left-drag lands on empty map area
    (pan) rather than on a token (token drag)."""
    box = page.eval_on_selector(
        "#map-pane",
        "el => {const r = el.getBoundingClientRect();"
        " return {x: r.x, y: r.y, w: r.width, h: r.height};}")
    # ~12% in from the top-left corner: inside the pane, away from tokens.
    return box["x"] + box["w"] * 0.12, box["y"] + box["h"] * 0.12


def test_left_drag_on_empty_canvas_pans_map(gm_page: Page):
    """Happy path: a left-button drag across empty map area changes the
    #map-transform translate()."""
    errors = _open_tabletop(gm_page)

    before = _transform(gm_page)
    sx, sy = _empty_canvas_point(gm_page)

    gm_page.mouse.move(sx, sy)
    gm_page.mouse.down()  # left button
    for i in range(1, 11):
        gm_page.mouse.move(sx + i * 14, sy + i * 9)
        gm_page.wait_for_timeout(8)
    gm_page.mouse.up()
    gm_page.wait_for_timeout(150)

    after = _transform(gm_page)
    assert after != before, (
        f"left-drag did not pan the map: transform unchanged ({before!r})")
    assert "translate(" in after, after
    assert not errors, f"JS errors during pan: {errors}"


def test_wheel_still_zooms(gm_page: Page):
    """Guard: the fix didn't regress wheel-zoom (the path that kept
    working when pan was broken)."""
    errors = _open_tabletop(gm_page)

    box = gm_page.eval_on_selector(
        "#map-pane",
        "el => {const r = el.getBoundingClientRect();"
        " return {x: r.x, y: r.y, w: r.width, h: r.height};}")
    cx, cy = box["x"] + box["w"] / 2, box["y"] + box["h"] / 2

    before = _transform(gm_page)
    gm_page.mouse.move(cx, cy)
    gm_page.mouse.wheel(0, -300)  # scroll up = zoom in
    gm_page.wait_for_timeout(150)

    after = _transform(gm_page)
    assert after != before, "wheel did not change the map transform (zoom)"
    assert "scale(" in after, after
    assert not errors, f"JS errors during zoom: {errors}"
