"""v2.871.0 — the lair-action zone overlay on the tabletop.

Lair zones placed in the editor render on the tabletop as a crimson overlay
(`.tt-lairzone`), toggled per-client by a 🎯 Zones button in the canvas-tools
cluster. The toggle is available to BOTH the GM and players (it's a targeting
aid, not GM-only), and the button only appears when the active map has zones.
"""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID

_ZONE = {"id": "z1", "x": 300, "y": 300, "w": 420, "h": 300,
         "label": "Magma vent", "actions": ["magma-erupts"]}


def _set_zones(zones) -> int:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lair_zones",
              json={"lair_zones": zones})
    return mid


def _count(page: Page) -> int:
    return page.eval_on_selector_all(".tt-lairzone", "els => els.length")


def test_gm_toggles_lair_zone_overlay(gm_page: Page) -> None:
    mid = _set_zones([_ZONE])
    try:
        gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
        gm_page.wait_for_selector("#wall-overlay", timeout=8000)
        gm_page.wait_for_timeout(700)

        btn = gm_page.locator("#lair-zones-btn")
        expect(btn).to_be_visible()          # map has zones → toggle surfaces
        assert _count(gm_page) == 0          # overlay off by default

        btn.click()
        gm_page.wait_for_timeout(300)
        assert _count(gm_page) >= 1          # toggled on → zone rendered
        assert btn.get_attribute("aria-pressed") == "true"

        # v2.873.0 — the zone label names its bound action (title-cased).
        labels = gm_page.eval_on_selector_all(
            "#wall-overlay text", "els => els.map(e => e.textContent)")
        assert any("Magma Erupts" in (t or "") for t in labels), labels

        btn.click()
        gm_page.wait_for_timeout(300)
        assert _count(gm_page) == 0          # toggled back off
    finally:
        _set_zones([])


def test_player_can_toggle_lair_zone_overlay(alice_page: Page) -> None:
    """The toggle + overlay are available to players too, not just the GM."""
    _set_zones([_ZONE])
    try:
        alice_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
        alice_page.wait_for_selector("#wall-overlay", timeout=8000)
        alice_page.wait_for_timeout(700)

        btn = alice_page.locator("#lair-zones-btn")
        expect(btn).to_be_visible()
        assert _count(alice_page) == 0
        btn.click()
        alice_page.wait_for_timeout(300)
        assert _count(alice_page) >= 1
    finally:
        _set_zones([])


def test_zones_button_hidden_when_no_zones(gm_page: Page) -> None:
    _set_zones([])
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
    gm_page.wait_for_selector("#wall-overlay", timeout=8000)
    gm_page.wait_for_timeout(600)
    # No zones on the map → the toggle stays hidden.
    expect(gm_page.locator("#lair-zones-btn")).to_be_hidden()
