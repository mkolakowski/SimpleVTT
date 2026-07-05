"""v2.907.0 — a selected embedded door can be moved (slide along the wall) and
resized (drag an edge handle). Selection is via the door's right-click menu."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID, me_clear_toolbar


def _door_hit_center(gm_page: Page):
    return gm_page.evaluate(
        """() => {
            const lines = [...document.querySelectorAll('#me-overlay line[stroke="transparent"]')];
            const dh = lines.find(l => {
                const t = l.querySelector('title');
                return t && /Door|Gate/.test(t.textContent)
                    && getComputedStyle(l).pointerEvents === 'stroke';
            });
            if (!dh) return null;
            const r = dh.getBoundingClientRect();
            return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
        }"""
    )


def _handle_centers(gm_page: Page):
    return gm_page.evaluate(
        """() => [...document.querySelectorAll('#me-overlay circle[fill="#ffd24a"]')].map(c => {
            const r = c.getBoundingClientRect();
            return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
        })"""
    )


def test_selected_door_resizes_and_moves(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": [
            {"id": "w", "x1": 200, "y1": 300, "x2": 700, "y2": 300, "style": "stone",
             "doors": [{"id": "d1", "t0": 0.4, "t1": 0.6, "open": False}]}]})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(300)
            me_clear_toolbar(gm_page)

            # Select the door via its right-click menu.
            dc = _door_hit_center(gm_page)
            assert dc, "no door hit-line found"
            gm_page.mouse.click(dc["x"], dc["y"], button="right")
            menu = gm_page.locator("#me-ctx-menu")
            expect(menu).to_be_visible()
            menu.locator("button", has_text="Move / resize").click()
            gm_page.wait_for_timeout(200)

            # Two yellow edge handles appear.
            handles = _handle_centers(gm_page)
            assert len(handles) == 2, handles

            # RESIZE: drag the rightmost handle further right → t1 grows.
            right = max(handles, key=lambda h: h["x"])
            gm_page.mouse.move(right["x"], right["y"])
            gm_page.mouse.down()
            gm_page.mouse.move(right["x"] + 90, right["y"], steps=6)
            gm_page.mouse.up()
            gm_page.wait_for_timeout(400)
            d = c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls").json()["walls"][0]["doors"][0]
            assert d["t1"] > 0.62, d  # widened

            # MOVE: drag the door body left → t0 shrinks (slides along the wall).
            t0_before = d["t0"]
            dc2 = _door_hit_center(gm_page)
            gm_page.mouse.move(dc2["x"], dc2["y"])
            gm_page.mouse.down()
            gm_page.mouse.move(dc2["x"] - 80, dc2["y"], steps=6)
            gm_page.mouse.up()
            gm_page.wait_for_timeout(400)
            d2 = c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls").json()["walls"][0]["doors"][0]
            assert d2["t0"] < t0_before, (t0_before, d2)  # slid left
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})
