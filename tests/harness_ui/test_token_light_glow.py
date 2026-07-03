"""v2.852.0 — token light sources glow (and flicker) on the light-glow layer.

A token carrying light (light_bright_ft/dim_ft) now contributes a warm,
torch-flickering glow on `#light-glow-canvas`, following the token as it moves.
Asserts the glow getter includes a lit token, the canvas draws at the token's
centre, the colour flickers across ~1s, and turning the light off (live via the
token PATCH → token_update WS) drops the token from the glow set.
"""
from __future__ import annotations

import httpx
from playwright.sync_api import Page

from .conftest import BASE_URL, CAMPAIGN_ID


def test_token_light_glows_and_flickers(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        toks = c.get(f"/api/campaign/{CAMPAIGN_ID}/tokens").json()["tokens"]
        assert toks, "demo campaign should have tokens"
        tk = toks[0]
        tid, tx, ty = tk["id"], float(tk["x"]), float(tk["y"])
        orig_b = tk.get("light_bright_ft", 0)
        # Grid is 70 on the flagship; the glow centres on the token cell centre.
        cx, cy = tx + 35, ty + 35
        # Light it up BEFORE loading so the /tokens bootstrap carries the light.
        c.patch(f"/api/campaign/{CAMPAIGN_ID}/token/{tid}",
                json={"light_bright_ft": 30, "light_dim_ft": 60})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
            gm_page.wait_for_function(
                "() => window._glowTokenLights && document.getElementById('light-glow-canvas')",
                timeout=8000)
            gm_page.wait_for_timeout(700)

            # The lit token is in the glow set.
            has_tok = gm_page.evaluate(
                "(id) => (window._glowTokenLights() || []).some(l => l.id === 'tok' + id)",
                tid)
            assert has_tok, "lit token should appear in the glow sources"

            sample = f"""() => {{
                const cv = document.getElementById('light-glow-canvas');
                const d = cv.getContext('2d').getImageData({int(cx)}, {int(cy)}, 1, 1).data;
                return [d[0], d[1], d[2], d[3]];
            }}"""
            s1 = gm_page.evaluate(sample)
            assert s1[3] > 0, f"glow should draw at the lit token: {s1}"
            gm_page.wait_for_timeout(750)
            s2 = gm_page.evaluate(sample)
            gm_page.wait_for_timeout(750)
            s3 = gm_page.evaluate(sample)
            assert s1 != s2 or s2 != s3, f"token glow should flicker: {s1} {s2} {s3}"

            # Turn the light off live → the WS token_update drops it from the set.
            c.patch(f"/api/campaign/{CAMPAIGN_ID}/token/{tid}",
                    json={"light_bright_ft": 0, "light_dim_ft": 0})
            gm_page.wait_for_timeout(600)
            still = gm_page.evaluate(
                "(id) => (window._glowTokenLights() || []).some(l => l.id === 'tok' + id)",
                tid)
            assert not still, "an unlit token should leave the glow set"
        finally:
            c.patch(f"/api/campaign/{CAMPAIGN_ID}/token/{tid}",
                    json={"light_bright_ft": int(orig_b or 0), "light_dim_ft": 0})
