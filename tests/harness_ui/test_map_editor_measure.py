"""v2.805.0 — the editor ruler / measure tool."""
from __future__ import annotations

import re

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID, me_clear_toolbar


def test_measure_shows_distance(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
    expect(gm_page.locator("#me-overlay")).to_be_visible()
    gm_page.wait_for_timeout(400)
    me_clear_toolbar(gm_page)  # map is full-bleed behind the toolbar
    gm_page.locator("#me-measure-btn").click()
    ov = gm_page.locator("#me-overlay").bounding_box()
    # Drag a ruler line across the overlay.
    gm_page.mouse.move(ov["x"] + 120, ov["y"] + 120)
    gm_page.mouse.down()
    gm_page.mouse.move(ov["x"] + 260, ov["y"] + 120, steps=5)
    gm_page.mouse.up()
    gm_page.wait_for_timeout(200)
    lbl = gm_page.locator("#me-overlay text.me-measure")
    assert lbl.count() >= 1
    txt = lbl.first.text_content()
    assert re.fullmatch(r"\d+ ft", txt), txt
    assert int(txt.split()[0]) > 0
    # The measurement clears when a different tool is armed.
    gm_page.locator("#me-wall-btn").click()
    gm_page.wait_for_timeout(150)
    assert gm_page.locator("#me-overlay text.me-measure").count() == 0
