"""v2.967.0 — doors show players (and the GM) their gate: a 🔒 badge on a
locked door and a 🎲 badge on a door that needs an open-check, rendered at the
door midpoint on the tabletop (closed doors only). Covers both a whole-segment
door and an embedded door.
"""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def test_locked_and_checked_doors_show_badges(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": [
            # A whole-segment door with an open-check → 🎲.
            {"id": "cd", "x1": 300, "y1": 250, "x2": 300, "y2": 400,
             "door": True, "open": False, "check": "Athletics", "dc": 15},
            # A wall with an embedded LOCKED door → 🔒.
            {"id": "lw", "x1": 600, "y1": 250, "x2": 600, "y2": 400,
             "doors": [{"id": "d1", "t0": 0.3, "t1": 0.7, "open": False,
                        "locked": True, "key": "Iron Key"}]},
        ]})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
            gm_page.wait_for_function(
                "() => typeof window.vttGetCharacters === 'function'", timeout=10000)
            gm_page.wait_for_timeout(600)  # let the wall overlay render
            badges = gm_page.evaluate(
                "() => [...document.querySelectorAll('svg text')].map(t => t.textContent)")
            assert any("🔒" in (b or "") for b in badges), badges
            assert any("🎲" in (b or "") for b in badges), badges
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})
