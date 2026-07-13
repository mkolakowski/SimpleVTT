"""v2.583.0 — left-drag on empty map area pans the tabletop map.
v2.1006.0 — scroll-to-pan is the default wheel scheme.

Regression net for the "map can't be moved" bug: right-button drag is
intercepted by the native context menu on macOS Safari / some trackpads,
so the map appeared stuck (zoom — a separate wheel path — still worked).
The fix adds left-drag-on-empty-canvas panning (the standard VTT gesture)
in tabletop.js's canvas mousedown/mousemove/mouseup handlers.

v2.1006.0 changed the wheel path: a bare wheel now PANS the map
(vertical → Y, horizontal / Shift+wheel → X) and Ctrl+wheel ZOOMS at
the cursor; the old bare-wheel-zoom scheme lives behind the per-user
"Alternative controls" setting (`ME.altControls`). The wheel tests
below assert the new default scheme; drag-pan is scheme-independent.

GM = gm_page (authenticated GM context on the tabletop).
"""
import re

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
    """A point just inside the MAP's top-left corner — derived from the
    live pan/zoom transform so it always lands ON the canvas (a fixed
    pane-percentage point can fall in the letterbox gutter left of the
    map when fit-to-viewport centers a tall map), while staying far
    from the mid-map area where demo tokens cluster (seeded ≥ 350 map
    px, i.e. well away from the 60-px corner inset used here)."""
    box = page.eval_on_selector(
        "#map-pane",
        "el => {const r = el.getBoundingClientRect();"
        " return {x: r.x, y: r.y, w: r.width, h: r.height};}")
    t = page.eval_on_selector("#map-transform", "el => el.style.transform")
    m = re.search(
        r"translate\((-?[\d.]+)px,\s*(-?[\d.]+)px\)\s*scale\((-?[\d.]+)\)",
        t or "")
    if not m:
        # No transform applied yet — the map fills from the pane origin.
        return box["x"] + 60, box["y"] + 60
    pan_x, pan_y = float(m.group(1)), float(m.group(2))
    return box["x"] + max(0.0, pan_x) + 60, box["y"] + max(0.0, pan_y) + 60


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


def _parse_transform(t: str):
    """Split `translate(Xpx, Ypx) scale(S)` into (x, y, s) floats."""
    m = re.search(
        r"translate\((-?[\d.]+)px,\s*(-?[\d.]+)px\)\s*scale\((-?[\d.]+)\)", t or "")
    assert m, f"unexpected transform shape: {t!r}"
    return float(m.group(1)), float(m.group(2)), float(m.group(3))


def _pane_center(page: Page):
    box = page.eval_on_selector(
        "#map-pane",
        "el => {const r = el.getBoundingClientRect();"
        " return {x: r.x, y: r.y, w: r.width, h: r.height};}")
    return box["x"] + box["w"] / 2, box["y"] + box["h"] / 2


def _settle_transform(page: Page):
    """Force a first applyTransform so style.transform is populated
    (a fresh GM view can start with an empty inline transform)."""
    cx, cy = _pane_center(page)
    page.mouse.move(cx, cy)
    page.mouse.wheel(0, 40)
    page.wait_for_timeout(120)
    return _transform(page)


def test_wheel_pans_by_default(gm_page: Page):
    """v2.1006.0 — the bare wheel PANS: translate changes, scale does
    not (the old bare-wheel zoom moved behind Alternative controls)."""
    errors = _open_tabletop(gm_page)
    before = _settle_transform(gm_page)
    bx, by, bs = _parse_transform(before)

    gm_page.mouse.wheel(0, -300)  # scroll up → pan up
    gm_page.wait_for_timeout(150)

    ax, ay, as_ = _parse_transform(_transform(gm_page))
    assert ay != by, f"wheel did not pan Y: {by} → {ay}"
    assert abs(as_ - bs) < 1e-9, f"bare wheel must not zoom: {bs} → {as_}"
    assert not errors, f"JS errors during wheel pan: {errors}"


def test_shift_wheel_pans_horizontally(gm_page: Page):
    """v2.1006.0 — Shift+vertical-wheel pans the X axis (the axis-swap
    for mice without a horizontal wheel)."""
    errors = _open_tabletop(gm_page)
    before = _settle_transform(gm_page)
    bx, by, bs = _parse_transform(before)

    gm_page.keyboard.down("Shift")
    gm_page.mouse.wheel(0, -300)
    gm_page.keyboard.up("Shift")
    gm_page.wait_for_timeout(150)

    ax, ay, as_ = _parse_transform(_transform(gm_page))
    assert ax != bx, f"Shift+wheel did not pan X: {bx} → {ax}"
    assert abs(as_ - bs) < 1e-9, f"Shift+wheel must not zoom: {bs} → {as_}"
    assert not errors, f"JS errors during shift-wheel pan: {errors}"


def test_ctrl_wheel_zooms(gm_page: Page):
    """v2.1006.0 — Ctrl+wheel ZOOMS at the cursor (and trackpad pinch,
    which the browser reports as a ctrlKey wheel, rides the same path)."""
    errors = _open_tabletop(gm_page)
    before = _settle_transform(gm_page)
    _, _, bs = _parse_transform(before)

    gm_page.keyboard.down("Control")
    gm_page.mouse.wheel(0, -300)  # scroll up = zoom in
    gm_page.keyboard.up("Control")
    gm_page.wait_for_timeout(150)

    _, _, as_ = _parse_transform(_transform(gm_page))
    assert as_ > bs, f"Ctrl+wheel did not zoom in: scale {bs} → {as_}"
    assert not errors, f"JS errors during ctrl-wheel zoom: {errors}"
