"""v2.913.0 — the map editor's per-map default token-size dial (Grid group)
persists to the map and grows the sample-token preview."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def test_editor_token_scale_persists_and_scales_preview(gm_page: Page) -> None:
    gm_page.set_viewport_size({"width": 1800, "height": 1000})
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(400)

            # Drop one sample token (the preview starts empty) + read its radius.
            gm_page.locator("#me-token-btn").click()
            expect(gm_page.locator(".me-token")).to_have_count(1)
            r_before = gm_page.eval_on_selector(
                "#me-overlay .me-token circle", "el => parseFloat(el.getAttribute('r'))")

            # Dial the per-map token scale up to 2×.
            inp = gm_page.locator("#me-token-scale")
            inp.fill("2")
            inp.dispatch_event("change")
            gm_page.wait_for_timeout(500)

            # The preview token grew (roughly doubled from the 1× baseline).
            r_after = gm_page.eval_on_selector(
                "#me-overlay .me-token circle", "el => parseFloat(el.getAttribute('r'))")
            assert r_after > r_before * 1.5, (r_before, r_after)

            # It persisted to the map.
            am = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()
            assert am["token_scale"] == 2.0, am
        finally:
            c.post(f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/token_scale",
                   json={"token_scale": 1.0})
