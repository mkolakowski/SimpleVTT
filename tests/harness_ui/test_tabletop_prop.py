"""v2.793.0 — decorative prop stamps render on the tabletop."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page

from .conftest import BASE_URL, CAMPAIGN_ID


def test_tabletop_renders_props(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/props", json={"props": [
            {"x": 120, "y": 130, "kind": "🌲", "size": 48, "rot": 0}]})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
            gm_page.wait_for_function(
                "() => typeof window._onPropsUpdate === 'function'", timeout=8000)
            # Push a props update over the WS path + assert the glyph renders.
            gm_page.evaluate("""() => window._onPropsUpdate({ props: [
                { id: 'pr', x: 120, y: 130, kind: '🌲', size: 48, rot: 0 }] })""")
            gm_page.wait_for_timeout(200)
            glyphs = gm_page.eval_on_selector_all(
                "#wall-overlay text.tt-prop",
                "els => els.map(e => e.textContent)")
            assert "🌲" in glyphs, glyphs
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/props", json={"props": []})
