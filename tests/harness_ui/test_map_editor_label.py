"""v2.803.0 — placing public text labels in the map editor."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def test_place_label(gm_page: Page) -> None:
    gm_page.on("dialog", lambda d: d.accept("The Vault"))
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/labels", json={"labels": []})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(400)
            gm_page.locator("#me-label-btn").click()
            ov = gm_page.locator("#me-overlay").bounding_box()
            gm_page.mouse.click(ov["x"] + 150, ov["y"] + 120)
            gm_page.wait_for_timeout(300)
            labels = c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/labels").json()["labels"]
            assert len(labels) == 1 and labels[0]["text"] == "The Vault", labels
            lbl = gm_page.locator("#me-overlay text.me-label")
            assert lbl.count() == 1
            assert lbl.first.text_content() == "The Vault"
            # Hiding the Labels layer removes it.
            gm_page.uncheck("#me-layer-labels")
            gm_page.wait_for_timeout(200)
            assert gm_page.locator("#me-overlay text.me-label").count() == 0
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/labels", json={"labels": []})
