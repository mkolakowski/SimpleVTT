"""v2.823.0 — grab-and-drag panning of the map editor (tabletop-style camera).

v2.828.0 — panning is now a CSS-transform camera (overflow:hidden), so it works
even when the map fits the frame. The overlay/image are translated together;
we read the translate from the overlay's computed transform matrix.
"""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID

# Read the camera offset off the overlay's computed transform (identity → 0,0).
_PAN_JS = ("el => { const m = new DOMMatrixReadOnly(getComputedStyle(el).transform);"
           " return {x: m.m41, y: m.m42}; }")


def _open(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
    expect(gm_page.locator("#me-overlay")).to_be_visible()
    gm_page.wait_for_timeout(400)


def _drag(gm_page: Page, button: str = "left") -> None:
    box = gm_page.locator("#me-stage").bounding_box()
    # Grab near the top edge (in-viewport) and drag down-right so the camera
    # offset grows in both axes and the end point stays on-screen.
    sx, sy = box["x"] + box["width"] / 2, box["y"] + 80
    gm_page.mouse.move(sx, sy)
    gm_page.mouse.down(button=button)
    gm_page.mouse.move(sx + 150, sy + 150, steps=12)
    gm_page.mouse.up(button=button)
    gm_page.wait_for_timeout(120)


def test_drag_pans_the_map(gm_page: Page) -> None:
    _open(gm_page)

    # The stage advertises itself as pannable with a grab cursor.
    assert gm_page.eval_on_selector("#me-stage", "el => getComputedStyle(el).cursor") == "grab"

    before = gm_page.eval_on_selector("#me-overlay", _PAN_JS)
    _drag(gm_page)  # no tool active → left-drag pans
    after = gm_page.eval_on_selector("#me-overlay", _PAN_JS)
    # Dragging down-right moves the camera down-right: both offsets grow.
    assert after["x"] > before["x"] + 40, (before, after)
    assert after["y"] > before["y"] + 40, (before, after)


def test_middle_button_pans_with_tool_active(gm_page: Page) -> None:
    """v2.824.0 — the middle button pans even while a drawing tool is active."""
    _open(gm_page)

    # Activate the Wall tool (left-drag now draws, so it must NOT pan).
    gm_page.keyboard.press("w")
    gm_page.wait_for_timeout(80)
    assert gm_page.locator("#me-wall-btn").get_attribute("aria-pressed") == "true"

    before = gm_page.eval_on_selector("#me-overlay", _PAN_JS)
    _drag(gm_page, button="middle")
    after = gm_page.eval_on_selector("#me-overlay", _PAN_JS)
    assert after["x"] > before["x"] + 40, (before, after)
    assert after["y"] > before["y"] + 40, (before, after)
