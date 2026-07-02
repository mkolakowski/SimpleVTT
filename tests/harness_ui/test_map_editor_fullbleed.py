"""v2.829.0 — full-bleed, tabletop-style editor: the map fills the whole screen
below a transparent toolbar strip; the toolbar stays in flow (never over the
drawing canvas) so it can't block drawing."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def test_fullbleed_layout(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
    expect(gm_page.locator("#me-overlay")).to_be_visible()
    gm_page.wait_for_timeout(300)

    stage = gm_page.locator("#me-stage").bounding_box()
    toolbar = gm_page.locator(".me-toolbar").bounding_box()
    vh = gm_page.viewport_size["height"]

    # The map stage is wide and fills the screen all the way to the bottom edge
    # (full-bleed), taking whatever vertical space the toolbar leaves.
    assert stage["width"] > 700, stage
    assert stage["y"] + stage["height"] >= vh - 24, (stage, vh)

    # The toolbar sits ABOVE the map (its bottom is at/above the stage top), so
    # it never covers the drawing canvas.
    assert toolbar["y"] + toolbar["height"] <= stage["y"] + 2, (toolbar, stage)

    # The transparent bar keeps its backdrop blur.
    blur = gm_page.eval_on_selector(
        ".me-toolbar",
        "el => getComputedStyle(el).backdropFilter || getComputedStyle(el).webkitBackdropFilter")
    assert "blur" in (blur or ""), blur

    # The version footer is suppressed so the map reaches the bottom edge.
    assert gm_page.locator(".site-footer").count() == 0
