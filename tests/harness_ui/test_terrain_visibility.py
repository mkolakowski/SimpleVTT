"""v2.858.0 — GM reveal-terrain toggle on the tabletop.

Terrain is hidden from players by default: a player sees no terrain overlay
while the GM does. After the GM reveals it (GM Tools → Terrain), the player's
tabletop shows the terrain live via the `terrain_visibility_update` broadcast.
"""
from __future__ import annotations

import httpx
from playwright.sync_api import Page

from .conftest import BASE_URL, CAMPAIGN_ID


def _terrain_polys(page: Page) -> int:
    return page.evaluate(
        "() => document.querySelectorAll('#wall-overlay polygon, #wall-overlay rect').length")


def test_player_hidden_gm_sees_then_reveal(gm_page: Page, alice_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        saved = c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/terrain").json()["terrain"]
        # A clear water polygon + hidden-by-default.
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/terrain", json={"terrain": [
            {"id": "tv", "type": "water",
             "points": [[300, 300], [500, 320], [520, 500], [340, 520]]}]})
        c.post(f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/terrain_visibility",
               json={"hidden": True})
        try:
            # Player: no terrain overlay while hidden.
            alice_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
            alice_page.wait_for_selector("#wall-overlay", timeout=8000)
            alice_page.wait_for_timeout(800)
            assert _terrain_polys(alice_page) == 0, "player should not see hidden terrain"

            # GM: sees the terrain, and has the reveal toggle in GM Tools.
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
            gm_page.wait_for_selector("#wall-overlay", timeout=8000)
            gm_page.wait_for_timeout(800)
            assert _terrain_polys(gm_page) >= 1, "GM should always see terrain"
            assert gm_page.locator("#terrain-reveal-btn").count() == 1, "GM has the toggle"
            # A player never gets the GM-only toggle.
            assert alice_page.locator("#terrain-reveal-btn").count() == 0

            # GM reveals (drives the same wired handler the toggle button uses)
            # → the player's tabletop shows it live via the broadcast.
            gm_page.evaluate("() => window.setTerrainVisibility(false)")
            gm_page.wait_for_timeout(600)
            alice_page.wait_for_timeout(600)
            assert _terrain_polys(alice_page) >= 1, "player should see revealed terrain"
        finally:
            c.post(f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/terrain_visibility",
                   json={"hidden": True})
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/terrain", json={"terrain": saved})
