"""v2.821.0 — single-key tool hotkeys in the map editor."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def _open_editor(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
    expect(gm_page.locator("#me-overlay")).to_be_visible()
    gm_page.wait_for_timeout(300)


def test_tool_hotkey_toggles_mode(gm_page: Page) -> None:
    _open_editor(gm_page)
    wall = gm_page.locator("#me-wall-btn")
    door = gm_page.locator("#me-door-btn")
    assert wall.get_attribute("aria-pressed") == "false"

    # "w" activates the Wall tool.
    gm_page.keyboard.press("w")
    gm_page.wait_for_timeout(80)
    assert wall.get_attribute("aria-pressed") == "true"

    # "d" switches to Door (only one mode active at a time).
    gm_page.keyboard.press("d")
    gm_page.wait_for_timeout(80)
    assert door.get_attribute("aria-pressed") == "true"
    assert wall.get_attribute("aria-pressed") == "false"

    # "d" again toggles Door back off.
    gm_page.keyboard.press("d")
    gm_page.wait_for_timeout(80)
    assert door.get_attribute("aria-pressed") == "false"

    # The shortcut is surfaced in the tooltip.
    assert "shortcut: W" in (wall.get_attribute("title") or "")


def test_label_tool_hotkey(gm_page: Page) -> None:
    """v2.866.0 — the Label tool ('a') was the last placement tool without a
    hotkey; 'a' now activates it and the tooltip advertises the shortcut."""
    _open_editor(gm_page)
    label = gm_page.locator("#me-label-btn")
    assert label.get_attribute("aria-pressed") == "false"

    gm_page.keyboard.press("a")
    gm_page.wait_for_timeout(80)
    assert label.get_attribute("aria-pressed") == "true"
    assert "shortcut: A" in (label.get_attribute("title") or "")

    # 'a' again toggles it back off (one mode at a time).
    gm_page.keyboard.press("a")
    gm_page.wait_for_timeout(80)
    assert label.get_attribute("aria-pressed") == "false"


def test_hotkey_ignored_while_typing(gm_page: Page) -> None:
    _open_editor(gm_page)
    wall = gm_page.locator("#me-wall-btn")
    # Focus a numeric field and type "w" — the tool must NOT activate.
    gm_page.locator("#me-ambient").focus()
    gm_page.keyboard.press("w")
    gm_page.wait_for_timeout(80)
    assert wall.get_attribute("aria-pressed") == "false"
