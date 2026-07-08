"""v2.964.2 — map-editor incremental saves fire the bottom-center toast
(``.me-toast`` at left:50%; bottom:28px), not just the small top status text.
Triggering a save (here: "Insert door here", which calls saveWalls) shows it.
"""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID, me_clear_toolbar


def test_save_shows_bottom_center_toast(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": [
            {"id": "w", "x1": 200, "y1": 300, "x2": 700, "y2": 300, "style": "stone"}]})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(300)
            me_clear_toolbar(gm_page)

            # Right-click the wall → "Insert door here" (calls saveWalls → toast).
            box = gm_page.locator('#me-overlay line[stroke="transparent"]').first.bounding_box()
            gm_page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2,
                                button="right")
            menu = gm_page.locator("#me-ctx-menu")
            expect(menu).to_be_visible()
            menu.locator("button", has_text="Insert door").click()

            # The bottom-center toast pops with the save confirmation.
            toast = gm_page.locator(".me-toast.me-toast--show")
            expect(toast).to_be_visible(timeout=3000)
            expect(toast).to_contain_text("Saved")
            # It's anchored bottom-center (left:50% + translateX(-50%)).
            centered = gm_page.evaluate(
                """() => {
                    const t = document.querySelector('.me-toast');
                    const r = t.getBoundingClientRect();
                    const cx = r.left + r.width / 2;
                    return Math.abs(cx - window.innerWidth / 2) < 40
                        && r.top > window.innerHeight / 2;
                }""")
            assert centered, "toast should sit in the bottom-center of the display"
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})
