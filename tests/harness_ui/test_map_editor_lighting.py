"""v2.774.0 — light illumination preview in the map editor.

On a dark map, the editor renders the lighting (veil + light punches + wall
shadows) like the tabletop, so the GM sees what the lights illuminate. Sampled
via `window.__meLightCanvas` (natural map-pixel coords).
"""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def test_editor_renders_light_illumination(gm_page: Page) -> None:
    errors: list[str] = []
    gm_page.on("pageerror", lambda e: errors.append(str(e)))
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.post(f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/ambient_light",
               json={"ambient_light": "dark"})
        # A small light (≈10/15 ft → ~140/210 px) so the far corner stays dark.
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights",
              json={"lights": [{"x": 400, "y": 400, "bright_ft": 10, "dim_ft": 15}]})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_function("() => window.__meLightCanvas", timeout=8000)
            gm_page.wait_for_timeout(500)

            res = gm_page.evaluate("""() => {
                const cx = window.__meLightCanvas.getContext('2d');
                const a = (x, y) => cx.getImageData(x, y, 1, 1).data[3];
                return { lit: a(403, 400), dark: a(800, 800) };
            }""")
            # Near the light → cleared; far point (outside the radius) → veiled.
            assert res["lit"] < 60, res
            assert res["dark"] > 150, res
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights", json={"lights": []})
            c.post(f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/ambient_light",
                   json={"ambient_light": "bright"})

    assert not errors, f"JS errors: {errors}"
