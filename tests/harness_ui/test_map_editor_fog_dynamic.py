"""v2.845.0 — the map editor's dynamic-fog (exploration) toggle + reset.

Entering Fog mode surfaces the "explore (dynamic)" checkbox; ticking it turns
fog on, persists `fog_dynamic` through the fog PUT, and reveals the "Reset
explored" button. The reset button clears accumulated `fog_explored`.
"""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def test_editor_dynamic_fog_toggle_and_reset(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        # Start clean: fog off, not dynamic, with some explored memory to clear.
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/fog",
              json={"enabled": False, "dynamic": False, "revealed": []})
        c.post(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/fog/explore",
               json={"cells": [[1, 1], [2, 2]]})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(300)

            # v2.938.0 — the fog controls are always visible now (the fog-mode
            # paint button was removed); no need to enter a mode first.
            expect(gm_page.locator("#me-fog-dyn-lbl")).to_be_visible()
            expect(gm_page.locator("#me-fog-on-cb")).to_be_visible()

            # Tick "explore (dynamic)" → fog_dynamic persists via the fog PUT.
            gm_page.check("#me-fog-dyn-cb")
            gm_page.wait_for_timeout(400)
            fog = c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/fog").json()
            assert fog["fog_dynamic"] is True, fog
            assert fog["fog_enabled"] is True, fog   # exploring implies fog on

            # The reset button is now visible; clicking it clears explored memory.
            expect(gm_page.locator("#me-fog-reset-btn")).to_be_visible()
            gm_page.click("#me-fog-reset-btn")
            gm_page.wait_for_timeout(400)
            assert c.get(
                f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/fog").json()["fog_explored"] == []
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/fog",
                  json={"enabled": False, "dynamic": False, "revealed": []})
            c.post(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/fog/reset")
