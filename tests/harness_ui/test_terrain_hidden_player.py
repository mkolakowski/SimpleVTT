"""v2.890.0 — a per-region-hidden terrain region is drawn for the GM but not
for players (independent of the map-level terrain_hidden toggle)."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page

from .conftest import BASE_URL, CAMPAIGN_ID, tabletop_url


def _terrain_labels(page: Page) -> list[str]:
    # Terrain labels render as <text> in the #wall-overlay SVG.
    return page.eval_on_selector_all(
        "#wall-overlay text",
        "els => els.map(e => e.textContent)",
    )


def _seed(mid: int) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        # Map-level terrain VISIBLE, so only the per-region flag hides anything.
        c.post(f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/terrain_visibility",
               json={"hidden": False})
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/terrain", json={"terrain": [
            {"id": "hid", "x": 120, "y": 120, "w": 90, "h": 90, "type": "lava", "hidden": True},
            {"id": "vis", "x": 400, "y": 120, "w": 90, "h": 90, "type": "water"},
        ]})


def _cleanup(mid: int) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/terrain", json={"terrain": []})
        c.post(f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/terrain_visibility",
               json={"hidden": True})


def test_player_hides_hidden_region_gm_sees_it(gm_page: Page, alice_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
    _seed(mid)
    try:
        # Player: sees the visible region's label, NOT the hidden one.
        alice_page.goto(tabletop_url())
        alice_page.wait_for_selector("#wall-overlay", timeout=8000)
        alice_page.wait_for_timeout(600)
        pl = " ".join(_terrain_labels(alice_page))
        assert "Water" in pl, pl
        assert "Lava" not in pl, pl

        # GM: sees BOTH, with the hidden one flagged 🔒.
        gm_page.goto(tabletop_url())
        gm_page.wait_for_selector("#wall-overlay", timeout=8000)
        gm_page.wait_for_timeout(600)
        gm = " ".join(_terrain_labels(gm_page))
        assert "Water" in gm, gm
        assert "Lava" in gm and "🔒" in gm, gm
    finally:
        _cleanup(mid)
