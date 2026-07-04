"""v2.894.0 — the GM init-tracker lair panel pulls from the actions PLACED on
the map (zone-bound), even for a zone-driven lair with no creature owner."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID, tabletop_url

ZONE = {
    "id": "panel-z1", "x": 220, "y": 220, "w": 200, "h": 160,
    "label": "Magma vent", "actions": ["magma-erupts"], "color": "#d24b3a",
}


def test_init_panel_lists_placed_zone_action(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lair_zones", json={"lair_zones": [ZONE]})
    try:
        gm_page.goto(tabletop_url())
        gm_page.wait_for_function(
            "() => window._lairCatalog && window._lairCatalog['magma-erupts'] "
            "&& typeof window._renderLairActionPanel === 'function'", timeout=8000)
        # Simulate a running combat whose only combatant has NO lair actions
        # (the client builds battle state live via WS; we inject an equivalent
        # active battle), then render the panel. A zone-driven lair (no creature
        # owner) must still surface, sourcing its action from the placed zone.
        gm_page.evaluate(
            """() => {
                window.battle = {
                    active: true, in_lair: true, lair_slug: '', round: 1, turn_index: 0,
                    combatants: [{ id: 'pf', name: 'Goblin', initiative: 12,
                        hp_current: 7, hp_max: 7, buffs: [],
                        economy: { action: false, bonus: false, reaction: false, movement: 0 } }],
                };
                window._renderLairActionPanel();
            }"""
        )
        panel = gm_page.locator("#_lair_action_panel")
        expect(panel).to_contain_text("Magma Erupts")
    finally:
        with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
            c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
            mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lair_zones", json={"lair_zones": []})
