"""v2.823.0 — grab-and-drag panning of the map editor stage (tabletop-style)."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def test_drag_pans_the_stage(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
    expect(gm_page.locator("#me-overlay")).to_be_visible()
    gm_page.wait_for_timeout(300)

    # The stage advertises itself as pannable with a grab cursor.
    cursor = gm_page.eval_on_selector("#me-stage", "el => getComputedStyle(el).cursor")
    assert cursor == "grab", cursor

    # Zoom in so the map overflows the stage (otherwise there's nothing to pan).
    for _ in range(4):
        gm_page.locator("#me-zoom-in").click()
        gm_page.wait_for_timeout(50)
    gm_page.wait_for_timeout(150)

    before = gm_page.eval_on_selector(
        "#me-stage", "el => ({x: el.scrollLeft, y: el.scrollTop})")

    # Grab the map near its top edge (kept in-viewport — the tall stage's centre
    # can fall below the fold) and drag up-left → the stage scrolls right/down.
    gm_page.locator("#me-stage").scroll_into_view_if_needed()
    box = gm_page.locator("#me-stage").bounding_box()
    sx, sy = box["x"] + box["width"] / 2, box["y"] + 100
    gm_page.mouse.move(sx, sy)
    gm_page.mouse.down()
    gm_page.mouse.move(sx - 160, sy - 80, steps=12)
    gm_page.mouse.up()
    gm_page.wait_for_timeout(120)

    after = gm_page.eval_on_selector(
        "#me-stage", "el => ({x: el.scrollLeft, y: el.scrollTop})")
    # Dragging left/up scrolls the content right/down: both offsets grow.
    assert after["x"] > before["x"], (before, after)
    assert after["y"] > before["y"], (before, after)
