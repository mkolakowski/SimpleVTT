"""v2.908.0 — placeable tools are single-shot by default (auto-off after one
placement) and "sticky" (stay armed, yellow ring) when right-clicked."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID, me_clear_toolbar


def _open_editor(gm_page: Page):
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights", json={"lights": []})
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
    expect(gm_page.locator("#me-overlay")).to_be_visible()
    gm_page.wait_for_timeout(300)
    me_clear_toolbar(gm_page)
    return mid


def _clear(mid: int):
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights", json={"lights": []})


def test_left_click_tool_is_single_shot(gm_page: Page) -> None:
    mid = _open_editor(gm_page)
    try:
        lb = gm_page.locator("#me-light-btn")
        lb.click()  # left-click arms the tool
        assert lb.get_attribute("aria-pressed") == "true"
        ov = gm_page.locator("#me-overlay").bounding_box()
        gm_page.mouse.click(ov["x"] + ov["width"] * 0.4, ov["y"] + 60)  # place one light
        gm_page.wait_for_timeout(400)
        # Single-shot: the tool turned itself off after the placement.
        assert lb.get_attribute("aria-pressed") == "false"
    finally:
        _clear(mid)


def test_right_click_tool_is_sticky(gm_page: Page) -> None:
    mid = _open_editor(gm_page)
    try:
        lb = gm_page.locator("#me-light-btn")
        lb.click(button="right")  # right-click arms it in sticky mode
        assert lb.get_attribute("aria-pressed") == "true"
        assert "me-tool-sticky" in (lb.get_attribute("class") or "")
        ov = gm_page.locator("#me-overlay").bounding_box()
        gm_page.mouse.click(ov["x"] + ov["width"] * 0.4, ov["y"] + 60)  # place one light
        gm_page.wait_for_timeout(400)
        # Sticky: still armed for the next placement (ring still shown).
        assert lb.get_attribute("aria-pressed") == "true"
        assert "me-tool-sticky" in (lb.get_attribute("class") or "")
    finally:
        _clear(mid)
