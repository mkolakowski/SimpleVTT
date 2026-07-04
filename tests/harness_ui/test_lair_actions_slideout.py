"""v2.892.0 — the placed-lair-actions slide-out.

A 📋 button (shown when the map has lair actions bound to zones) opens a right
slide-out listing every placed lair action; hovering a row highlights that
action's zone(s) on the map.
"""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID, tabletop_url

ZONE = {
    "id": "slideout-z1", "x": 200, "y": 200, "w": 200, "h": 160,
    "label": "Magma vent", "actions": ["magma-erupts"], "color": "#d24b3a",
}


def _seed_zone(mid: int) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lair_zones",
              json={"lair_zones": [ZONE]})


def _cleanup(mid: int) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lair_zones", json={"lair_zones": []})


def test_slideout_lists_placed_action_and_hover_highlights(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
    _seed_zone(mid)
    try:
        gm_page.goto(tabletop_url())
        # Wait for the map + the mechanics catalog to load.
        gm_page.wait_for_function(
            "() => window._lairCatalog && window._lairCatalog['magma-erupts']", timeout=8000)
        gm_page.wait_for_timeout(300)

        # The list button surfaces (the map has a bound action) → open it.
        btn = gm_page.locator("#lair-actions-list-btn")
        expect(btn).to_be_visible()
        btn.click()

        body = gm_page.locator("#lair-actions-slideout-body")
        expect(body).to_contain_text("Magma Erupts")
        # GM sees the mechanics meta.
        expect(body).to_contain_text("6d6")

        # Hovering the row highlights the bound zone (flash styling on the SVG).
        gm_page.locator("#lair-actions-slideout-body > div").first.hover()
        gm_page.wait_for_timeout(200)
        op = gm_page.eval_on_selector(".tt-lairzone", "e => e.getAttribute('fill-opacity')")
        assert op == "0.42", op  # flashed/highlighted opacity (vs 0.18 idle)
    finally:
        _cleanup(mid)


def test_gm_slideout_row_has_trigger_button_player_does_not(
    gm_page: Page, alice_page: Page,
) -> None:
    """v2.893.0 — the GM's slide-out rows carry a ⚡ Trigger button (roll the
    placed action); a player's rows do not (list-only, no mechanics)."""
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
    _seed_zone(mid)
    try:
        # GM sees a Trigger button.
        gm_page.goto(tabletop_url())
        gm_page.wait_for_function(
            "() => window._lairCatalog && window._lairCatalog['magma-erupts']", timeout=8000)
        gm_page.locator("#lair-actions-list-btn").click()
        expect(gm_page.locator("#lair-actions-slideout-body button", has_text="Trigger")).to_be_visible()
        # The GM's structured mechanics meta line (💥 damage) is present.
        assert "💥" in gm_page.locator("#lair-actions-slideout-body").inner_text()

        # Player: same list, but NO Trigger button and no structured meta line
        # (the SRD flavour text may still narrate the dice — that's fine).
        alice_page.goto(tabletop_url())
        alice_page.wait_for_function(
            "() => window._lairCatalog && window._lairCatalog['magma-erupts']", timeout=8000)
        alice_page.locator("#lair-actions-list-btn").click()
        body = alice_page.locator("#lair-actions-slideout-body")
        expect(body).to_contain_text("Magma Erupts")
        assert body.locator("button", has_text="Trigger").count() == 0
        assert "💥" not in body.inner_text(), "player should not see the structured mechanics meta"
    finally:
        _cleanup(mid)
