"""v2.49.92 — canvas pan + drag regression tests.

Two failed iPad text-select attempts (v2.49.88 CSS, v2.49.90
selectstart JS) both ended up breaking pan / drag in ways the existing
HTTP+WS harness could not detect — those tests can't reach the canvas
event handlers. This suite drives a real browser against the demo
tabletop and asserts the load-bearing canvas interactions:

  * right-click drag pans the map (canvas ``style.transform`` mutates)
  * left-click drag on a token moves the token (the canvas re-renders
    at the new world-space coords; we observe the WS broadcast via
    the network log + assert the new coords stick)
  * the page loads with no JavaScript console errors

Any future "fix" for the iPad text-select issue MUST keep these tests
green. If a CSS or JS change suppresses pointer / mousedown events on
``#vtt-canvas`` or ``.map-pane``, the pan/drag asserts will fail and
catch the regression before merge — exactly the gap v2.49.88 +
v2.49.90 fell into.
"""
from __future__ import annotations

import re

from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


_TRANSLATE_RE = re.compile(r"translate\(\s*(-?\d+(?:\.\d+)?)px\s*,\s*(-?\d+(?:\.\d+)?)px\s*\)")


def _parse_translate(transform: str) -> tuple[float, float]:
    """Pull (panX, panY) out of a CSS ``transform: translate(Xpx, Ypx)
    scale(...)`` string. Returns (0, 0) if there's no translate
    component (e.g. before any pan happens applyTransform() has run
    and set ``translate(0px, 0px) scale(1)``)."""
    m = _TRANSLATE_RE.search(transform or "")
    if not m:
        return (0.0, 0.0)
    return (float(m.group(1)), float(m.group(2)))


def _wait_for_tabletop_ready(page: Page) -> None:
    """The tabletop attaches its mousedown / mouseup / wheel handlers
    inside an IIFE that runs after the canvas + tokens are fetched.
    Wait for both the canvas element AND for ``window.vttGetCharacters``
    to be defined — that global is assigned AFTER the mousedown
    listener is registered, so its presence proves the IIFE finished
    attaching the handlers we want to exercise.

    Initial ``style.transform`` would be a flakier signal: GMs without
    a saved view have an empty transform until they first interact,
    so polling for it could race the IIFE.
    """
    expect(page.locator("#vtt-canvas")).to_be_visible(timeout=8000)
    page.wait_for_function(
        "() => typeof window.vttGetCharacters === 'function'",
        timeout=5000,
    )


def test_tabletop_loads_without_js_errors(gm_page: Page) -> None:
    """Smoke: the tabletop renders for the GM and the IIFE that binds
    pan / drag handlers runs without throwing. v2.49.88 + v2.49.90
    were both syntactically valid but introduced runtime breakage; a
    bare load-and-check-console test would have caught neither
    because the errors were event-pipeline-level, not throw-level.
    This test sets the floor: no exceptions at load.
    """
    console_errors: list[str] = []
    gm_page.on("pageerror", lambda exc: console_errors.append(str(exc)))
    response = gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
    assert response is not None and response.ok, (
        f"Tabletop load failed: {response.status if response else 'no response'}"
    )
    _wait_for_tabletop_ready(gm_page)
    assert not console_errors, f"JS errors on tabletop load: {console_errors}"


def test_right_click_drag_pans_canvas(gm_page: Page) -> None:
    """The classic desktop pan gesture: right-mousedown, drag, mouseup.
    Asserts ``canvas.style.transform``'s translate(...) component
    shifts by approximately the drag delta (scale=1 at load, so the
    delta should match 1:1).

    This is the test that would have caught v2.49.88's CSS regression:
    after that commit's user-select / touch-callout rules landed, the
    right-click drag still fired mousedown but the pan never visibly
    happened — exactly what we assert against here.
    """
    console_errors: list[str] = []
    gm_page.on("pageerror", lambda exc: console_errors.append(str(exc)))
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
    _wait_for_tabletop_ready(gm_page)

    canvas = gm_page.locator("#vtt-canvas")
    # IMPORTANT — use the .map-pane bounding box, NOT the canvas's.
    # The canvas itself is 1500×1000 px (the world-space map size),
    # so its center can fall well outside the visible viewport.
    # ``.map-pane`` clips to the visible viewport and is always a
    # valid click target inside the visible area.
    map_pane_box = gm_page.locator(".map-pane").bounding_box()
    assert map_pane_box is not None, "Map pane has no bounding box"

    # v2.583.0: read the transform off ``#map-transform`` — the wrapper
    # the pan/zoom matrix has been applied to since the v2.88.0 single-
    # wrapper refactor. ``#vtt-canvas``'s own ``style.transform`` has
    # been empty since then, so this assertion read a dead element and
    # silently failed regardless of whether pan worked. Reading the
    # wrapper restores the intended right-click-pan regression coverage.
    initial_transform = gm_page.eval_on_selector("#map-transform", "el => el.style.transform")
    initial_x, initial_y = _parse_translate(initial_transform)

    # Right-click drag from map-pane center to +120, +80.
    start_x = map_pane_box["x"] + map_pane_box["width"] / 2
    start_y = map_pane_box["y"] + map_pane_box["height"] / 2
    end_x = start_x + 120
    end_y = start_y + 80

    gm_page.mouse.move(start_x, start_y)
    gm_page.mouse.down(button="right")
    # Multiple intermediate moves — some browsers gate the drag on
    # observed motion; a single jump from down to up doesn't count.
    gm_page.mouse.move(start_x + 30, start_y + 20)
    gm_page.mouse.move(start_x + 60, start_y + 40)
    gm_page.mouse.move(end_x, end_y)
    gm_page.mouse.up(button="right")

    # Allow the mousemove → applyTransform() → style write to settle.
    gm_page.wait_for_timeout(150)

    final_transform = gm_page.eval_on_selector("#map-transform", "el => el.style.transform")
    final_x, final_y = _parse_translate(final_transform)

    dx = final_x - initial_x
    dy = final_y - initial_y
    # clampPan() may constrain the final value — we don't assert exact
    # equality with (120, 80), just that motion happened in roughly
    # the right direction. ``> 20`` floor catches the "pan completely
    # blocked" regression (v2.49.88) while tolerating clamp behavior.
    assert dx > 20, (
        f"Right-click drag did NOT pan the canvas. Initial transform "
        f"{initial_transform!r}, final {final_transform!r}, dx={dx}, dy={dy}. "
        f"This is the v2.49.88 / v2.49.90 regression class — pointer events "
        f"on #vtt-canvas are being suppressed somewhere."
    )
    assert dy > 10, (
        f"Right-click drag pan didn't move vertically. dx={dx}, dy={dy}."
    )
    assert not console_errors, f"JS errors during pan: {console_errors}"


def test_left_click_drag_moves_token(gm_page: Page) -> None:
    """The other half of the canvas-interaction contract: left-click
    drag on a token moves it. The GM can move any token, so we don't
    have to log in as the specific player who owns one.

    We pick a token via the ``/api/campaign/{cid}/tokens`` JSON, drag
    from its world-space position (which == canvas pixel position at
    scale=1, pan=0,0) to (+200, +200), and then re-fetch tokens to
    confirm the server persisted the move. The WS broadcast is
    covered by the HTTP+WS harness; here we just need to prove the
    DOM-level drag fires end-to-end.
    """
    console_errors: list[str] = []
    gm_page.on("pageerror", lambda exc: console_errors.append(str(exc)))
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
    _wait_for_tabletop_ready(gm_page)

    # Pull a token to drag. Pip's the canonical demo PC; if his token
    # exists, use it. Fall back to whichever token API returns first.
    tokens_json = gm_page.evaluate(
        """async () => {
          const r = await fetch('/api/campaign/%d/tokens', {credentials: 'include'});
          return await r.json();
        }"""
        % CAMPAIGN_ID
    )
    tokens = tokens_json.get("tokens", [])
    assert tokens, "Demo has no tokens to drag"
    target = next((t for t in tokens if t.get("label") == "Pip Quickfingers"), tokens[0])
    token_id = target["id"]
    # Reset the token to a known on-screen position via the same
    # /token_move endpoint the canvas drag hits. The drag-test then
    # has a deterministic starting point regardless of where prior
    # test runs left this token. Pin to the upper-left quadrant
    # (one grid-cell offset from origin) so subsequent drags can't
    # push it off-screen.
    reset_world_x = 140.0
    reset_world_y = 140.0
    reset_result = gm_page.evaluate(
        """async ({tokenId, x, y}) => {
            const r = await fetch('/api/campaign/%d/token/' + tokenId + '/move', {
                method: 'POST',
                credentials: 'include',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({x: x, y: y, override: true}),
            });
            return {status: r.status, body: await r.text()};
        }"""
        % CAMPAIGN_ID,
        {"tokenId": token_id, "x": reset_world_x, "y": reset_world_y},
    )
    assert reset_result["status"] in (200, 201), (
        f"Token reset failed: {reset_result}"
    )
    # Reload so the canvas state reflects the reset position.
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
    _wait_for_tabletop_ready(gm_page)
    start_world_x = reset_world_x
    start_world_y = reset_world_y

    canvas = gm_page.locator("#vtt-canvas")
    box = canvas.bounding_box()
    assert box is not None
    grid_size = gm_page.evaluate("() => parseInt(document.getElementById('vtt-canvas').dataset.gridSize) || 50")
    # World→screen mapping mirrors the canvas's own ``clientToCanvas``:
    #   screen = box.start + (world + stripH) * scale
    # Two gotchas the original math missed (and which silently broke
    # this test once v2.88.0 landed + DPR ≠ 1):
    #   1. scale = box_size / offsetWidth. ``canvas.width`` can't be
    #      used as the divisor because it's DPR-scaled
    #      (``canvas.width = (MAP_W + 2*stripH) * DPR``); offsetWidth is
    #      the CSS layout width *before* the transform, so the ratio is
    #      the true on-screen scale.
    #   2. stripH — the v2.88.0 gutter the canvas is expanded by on
    #      every side (``canvas.dataset.stripH``). Logical (0,0) sits at
    #      canvas-local (stripH, stripH), so it must be added before
    #      scaling or the mousedown misses the token entirely.
    geo = gm_page.evaluate(
        "() => { const c = document.getElementById('vtt-canvas');"
        " return {offW: c.offsetWidth, offH: c.offsetHeight,"
        " strip: parseInt(c.dataset.stripH || '0', 10)}; }"
    )
    sx = box["width"] / geo["offW"]   # effective x-scale (CSS transform)
    sy = box["height"] / geo["offH"]  # effective y-scale
    strip = geo["strip"]
    cell_center_offset = grid_size / 2
    start_x = box["x"] + (start_world_x + cell_center_offset + strip) * sx
    start_y = box["y"] + (start_world_y + cell_center_offset + strip) * sy
    # Drag two grid cells right + one down in WORLD space, then map
    # the delta through the same scale so the screen-space move
    # matches.
    end_x = start_x + grid_size * 2 * sx
    end_y = start_y + grid_size * sy

    # Bail if the start point lands outside the visible map-pane —
    # an off-screen click won't dispatch to the canvas's listeners
    # and the test would fail for an unrelated reason. The current
    # demo's tokens (e.g. Pip at (350, 490)) are guaranteed inside
    # the pane at default load.
    map_pane_box = gm_page.locator(".map-pane").bounding_box()
    assert map_pane_box is not None
    in_pane = (
        map_pane_box["x"] <= start_x <= map_pane_box["x"] + map_pane_box["width"]
        and map_pane_box["y"] <= start_y <= map_pane_box["y"] + map_pane_box["height"]
    )
    assert in_pane, (
        f"Token {target['label']} at world ({start_world_x}, {start_world_y}) "
        f"maps to screen ({start_x:.0f}, {start_y:.0f}) which is outside the "
        f"visible map-pane {map_pane_box}. Test must pick a token that's "
        f"on-screen at default load."
    )

    gm_page.mouse.move(start_x, start_y)
    gm_page.mouse.down(button="left")
    gm_page.mouse.move(start_x + 25, start_y + 12)
    gm_page.mouse.move(start_x + 60, start_y + 30)
    gm_page.mouse.move(end_x, end_y)
    gm_page.mouse.up(button="left")

    # The mouseup handler POSTs /token_move and snaps to grid; give it
    # time to complete + broadcast. The token's authoritative position
    # then comes back from /api/campaign/{cid}/tokens.
    gm_page.wait_for_timeout(800)
    after_json = gm_page.evaluate(
        """async () => {
          const r = await fetch('/api/campaign/%d/tokens', {credentials: 'include'});
          return await r.json();
        }"""
        % CAMPAIGN_ID
    )
    after = next((t for t in after_json.get("tokens", []) if t["id"] == token_id), None)
    assert after is not None, f"Token {token_id} disappeared after drag"
    moved_x = abs(after["x"] - start_world_x) >= grid_size
    moved_y = abs(after["y"] - start_world_y) >= grid_size
    assert moved_x or moved_y, (
        f"Token {target['label']} (#{token_id}) did NOT move. "
        f"Before: ({start_world_x}, {start_world_y}), "
        f"After: ({after['x']}, {after['y']}). "
        f"This is the v2.49.88 / v2.49.90 regression class — left-click "
        f"drag on the canvas is not reaching the mousedown handler."
    )
    assert not console_errors, f"JS errors during drag: {console_errors}"


def test_zoom_in_supersamples_canvas(gm_page: Page) -> None:
    """v2.714.0 — supersample-on-zoom. Zooming in should re-raster the
    canvas at a HIGHER backing-store resolution (so high-res token sources
    stay crisp instead of the CSS transform bitmap-upscaling a fixed-res
    canvas). Asserts ``canvas.width`` (the backing store, not the CSS
    display size) grows after a zoom-in settles, and no JS errors fire.
    """
    console_errors: list[str] = []
    gm_page.on("pageerror", lambda exc: console_errors.append(str(exc)))
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
    _wait_for_tabletop_ready(gm_page)

    initial_w = gm_page.evaluate(
        "() => document.getElementById('vtt-canvas').width")
    assert initial_w and initial_w > 0

    pane = gm_page.locator(".map-pane").bounding_box()
    assert pane is not None, "Map pane has no bounding box"
    cx = pane["x"] + pane["width"] / 2
    cy = pane["y"] + pane["height"] / 2
    gm_page.mouse.move(cx, cy)
    # Many notches of zoom-in (deltaY < 0). The handler ignores magnitude
    # (only the sign), so each event is one zoom step.
    # v2.1006.0 — zoom now requires Ctrl+wheel (a bare wheel pans in the
    # default scroll-to-pan scheme), so hold Control for the notches.
    gm_page.keyboard.down("Control")
    for _ in range(14):
        gm_page.mouse.wheel(0, -120)
    gm_page.keyboard.up("Control")
    # Past the 180ms re-raster debounce.
    gm_page.wait_for_timeout(500)

    zoomed_w = gm_page.evaluate(
        "() => document.getElementById('vtt-canvas').width")
    # The CSS display size must stay the logical map size (transform math
    # depends on it) — only the backing store grows.
    css_w = gm_page.evaluate(
        "() => parseFloat(getComputedStyle(document.getElementById('vtt-canvas')).width)")
    assert zoomed_w > initial_w * 1.2, (
        f"Backing store did not supersample on zoom: {initial_w} -> {zoomed_w}")
    assert abs(css_w - initial_w) < 2 or css_w < zoomed_w, (
        f"CSS display width unexpectedly changed: css={css_w}, backing={zoomed_w}")
    assert not console_errors, f"JS errors during zoom: {console_errors}"


def test_quick_links_has_home_button(gm_page: Page) -> None:
    """v2.715.0 — the tabletop Quick Links panel includes a Home pill that
    points at the main page (`/`). Presence-only (the Tools drawer may be
    collapsed), so we assert the anchor exists with the right href + label
    rather than visibility."""
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
    _wait_for_tabletop_ready(gm_page)
    home = gm_page.locator('a.ql-pill[href="/"]')
    assert home.count() >= 1, "No Home quick-link pill found"
    # The Tools drawer may be collapsed, so use text_content() (returns text
    # regardless of visibility) rather than inner_text() (empty when hidden).
    assert "Home" in (home.first.text_content() or ""), (
        f"Home pill label unexpected: {home.first.text_content()!r}")


def test_feedback_page_files_and_lists_report(gm_page: Page) -> None:
    """v2.727.0 — the combined Feedback page (/my-suggestions) carries BOTH
    the file form and the reporter's own reports list. Files a report via the
    form, then (after the success reload) asserts it appears in the list."""
    console_errors: list[str] = []
    gm_page.on("pageerror", lambda exc: console_errors.append(str(exc)))
    gm_page.goto(f"{BASE_URL}/my-suggestions")
    expect(gm_page.locator("#file-suggestion-form")).to_be_visible()

    title = "UI combined-page report ZZZ"
    gm_page.select_option("#fs-kind", "issue")
    gm_page.fill("#fs-title", title)
    gm_page.fill("#fs-body", "Filed by the harness.")
    gm_page.click("#file-suggestion-form button[type='submit']")

    # The JS posts then reloads; the new report must show up in the list.
    expect(gm_page.locator("table.data")).to_contain_text(title, timeout=6000)
    assert not console_errors, f"JS errors during feedback flow: {console_errors}"


def test_topbar_controls_layer_above_left_roll_log(gm_page: Page) -> None:
    """v2.725.0 (TODO #876) — the left roll-log sidebar renders ABOVE the
    topbar's non-interactive bits (bar + campaign thumbnail) but BELOW the
    interactive controls (title pill + the ruler/tab-button card). Asserts
    the computed z-index ordering that encodes that contract."""
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
    _wait_for_tabletop_ready(gm_page)
    z = gm_page.evaluate(
        """() => {
            const g = sel => {
                const el = document.querySelector(sel);
                if (!el) return null;
                const v = parseInt(getComputedStyle(el).zIndex, 10);
                return Number.isNaN(v) ? 0 : v;
            };
            return {
                tab: g('.tt-tab-card'),
                title: g('.tt-title-pill'),
                thumb: g('.tt-topbar-thumb'),
                left: g('.drawer-sidebar--left'),
            };
        }"""
    )
    assert z["left"] is not None, "left sidebar missing"
    assert z["tab"] is not None and z["tab"] > z["left"], z
    assert z["title"] is not None and z["title"] > z["left"], z
    # The thumbnail (decoration) renders BELOW the roll log when present.
    if z["thumb"] is not None:
        assert z["thumb"] < z["left"], z
