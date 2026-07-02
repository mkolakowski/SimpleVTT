"""v2.838.0 — edge-to-edge editor: the map fills the whole editor and the
transparent toolbar floats OVER its top, like the main VTT. The bar container is
pointer-events:none so presses fall through to the map behind it; only the
controls capture input."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def test_fullbleed_overlay_layout(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
    expect(gm_page.locator("#me-overlay")).to_be_visible()
    gm_page.wait_for_timeout(300)

    stage = gm_page.locator("#me-stage").bounding_box()
    toolbar = gm_page.locator(".me-toolbar").bounding_box()
    vw = gm_page.viewport_size["width"]
    vh = gm_page.viewport_size["height"]

    # The map stage fills the editor edge-to-edge (full width + down to the bottom).
    assert stage["x"] <= 2 and stage["width"] >= vw - 4, (stage, vw)
    assert stage["y"] + stage["height"] >= vh - 4, (stage, vh)

    # The toolbar floats OVER the top of the map (absolute, inside the stage box).
    assert gm_page.eval_on_selector(".me-toolbar", "el => getComputedStyle(el).position") == "absolute"
    assert stage["y"] - 2 <= toolbar["y"] < stage["y"] + stage["height"], (toolbar, stage)

    # The bar container passes presses through to the map; only controls capture.
    assert gm_page.eval_on_selector(".me-toolbar", "el => getComputedStyle(el).pointerEvents") == "none"
    assert gm_page.eval_on_selector("#me-wall-btn", "el => getComputedStyle(el).pointerEvents") == "auto"

    # Still a transparent frosted bar, footer suppressed.
    blur = gm_page.eval_on_selector(
        ".me-toolbar",
        "el => getComputedStyle(el).backdropFilter || getComputedStyle(el).webkitBackdropFilter")
    assert "blur" in (blur or ""), blur
    assert gm_page.locator(".site-footer").count() == 0
