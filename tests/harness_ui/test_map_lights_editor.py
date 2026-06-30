"""v2.765.0 — placing a light source in the map editor.

Enters light mode, clicks the map (answering the bright/dim prompts), and
asserts a light persists server-side with the chosen radii + a ring renders.
"""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def test_editor_places_light(gm_page: Page) -> None:
    errors: list[str] = []
    gm_page.on("pageerror", lambda e: errors.append(str(e)))
    # Answer the two prompts (bright, then dim) in order.
    answers = iter(["25", "50"])
    gm_page.on("dialog", lambda d: d.accept(next(answers, "0")))
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights", json={"lights": []})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            overlay = gm_page.locator("#me-overlay")
            expect(overlay).to_be_visible()
            gm_page.locator("#me-light-btn").click()
            box = overlay.bounding_box()
            gm_page.mouse.click(box["x"] + 120, box["y"] + 120)
            gm_page.wait_for_timeout(400)

            lights = c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights").json()["lights"]
            assert len(lights) == 1, lights
            assert lights[0]["bright_ft"] == 25.0
            assert lights[0]["dim_ft"] == 50.0
            # A light marker rendered on the overlay.
            assert gm_page.locator("#me-overlay .me-light").count() == 1
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights", json={"lights": []})

    assert not errors, f"JS errors: {errors}"
