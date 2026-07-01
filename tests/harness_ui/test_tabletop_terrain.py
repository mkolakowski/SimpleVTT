"""v2.789.2 — terrain regions render on the tabletop."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page

from .conftest import BASE_URL, CAMPAIGN_ID


def test_tabletop_renders_terrain(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/terrain", json={"terrain": [
            {"x": 100, "y": 100, "w": 200, "h": 150, "type": "lava"}]})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
            gm_page.wait_for_function(
                "() => typeof window._onTerrainUpdate === 'function'", timeout=8000)
            # Push a terrain update over the WS path + assert a rect renders.
            gm_page.evaluate("""() => window._onTerrainUpdate({ terrain: [
                { id: 't', x: 100, y: 100, w: 200, h: 150, type: 'lava' }] })""")
            gm_page.wait_for_timeout(200)
            fill = gm_page.eval_on_selector_all(
                "#wall-overlay rect",
                "els => els.map(e => e.getAttribute('fill'))")
            assert "#d1481f" in fill, fill  # lava colour
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/terrain", json={"terrain": []})
