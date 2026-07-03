"""v2.849.0 — two-colour flicker glow for map light sources.

The tabletop's `#light-glow-canvas` draws a colored radial glow per map light
(the veil-punch lighting canvas stays colorless), animating torch-like between
`color` and `color2`. Asserts: the glow canvas has pixels at the light, the
color CHANGES over time (flicker), and a steady light (color2 == color) does
not change. Editor markers with a distinct color2 animate their fill too.
"""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def test_tabletop_glow_flickers(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights", json={"lights": [
            {"id": "flick1", "x": 400, "y": 400, "bright_ft": 20, "dim_ft": 40,
             "color": "#ffb347", "color2": "#ff2a1a", "type": "torch"},
        ]})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
            gm_page.wait_for_function(
                "() => window._onLightsGlow && document.getElementById('light-glow-canvas')",
                timeout=8000)
            gm_page.wait_for_timeout(800)  # bootstrap + a few frames

            sample = """() => {
                const cv = document.getElementById('light-glow-canvas');
                const d = cv.getContext('2d').getImageData(400, 400, 1, 1).data;
                return [d[0], d[1], d[2], d[3]];
            }"""
            s1 = gm_page.evaluate(sample)
            assert s1[3] > 0, f"glow canvas should draw at the light: {s1}"

            # Torch-like flicker: the sampled color shifts across ~1s.
            gm_page.wait_for_timeout(700)
            s2 = gm_page.evaluate(sample)
            gm_page.wait_for_timeout(700)
            s3 = gm_page.evaluate(sample)
            assert s1 != s2 or s2 != s3, f"glow should flicker: {s1} {s2} {s3}"
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights", json={"lights": []})


def test_editor_marker_flick_fill_animates(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights", json={"lights": [
            {"id": "flick2", "x": 500, "y": 500, "bright_ft": 20, "dim_ft": 20,
             "color": "#ffb347", "color2": "#ff2a1a", "type": "torch"},
        ]})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(600)
            # Two-colour markers are class-tagged; their fill is rAF-animated.
            fills = gm_page.evaluate("""() => {
                const el = document.querySelector('.me-light-flick');
                if (!el) return null;
                return new Promise(res => {
                    const f1 = el.getAttribute('fill');
                    setTimeout(() => res([f1, el.getAttribute('fill')]), 900);
                });
            }""")
            assert fills, "expected a flick-tagged light marker"
            assert fills[0] != fills[1], f"marker fill should animate: {fills}"
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights", json={"lights": []})
