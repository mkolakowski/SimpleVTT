"""v2.920.0 — double-clicking a wall or a door in the editor selects it into
move + resize mode. A door double-click does NOT toggle it open.
"""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID, me_clear_toolbar


def _handles(gm_page: Page):
    return gm_page.evaluate(
        """() => [...document.querySelectorAll('#me-overlay circle[fill="#ffd24a"]')].map(c => {
            const r = c.getBoundingClientRect();
            return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
        })"""
    )


def _wall_hit_center(gm_page: Page):
    return gm_page.evaluate(
        """() => {
            const l = [...document.querySelectorAll('#me-overlay line[stroke="transparent"]')]
                .find(l => getComputedStyle(l).pointerEvents !== 'none');
            if (!l) return null;
            const r = l.getBoundingClientRect();
            return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
        }"""
    )


def _door_hit_center(gm_page: Page):
    return gm_page.evaluate(
        """() => {
            const dh = [...document.querySelectorAll('#me-overlay line[stroke="transparent"]')]
                .find(l => { const t = l.querySelector('title');
                    return t && /Door|Gate/.test(t.textContent)
                        && getComputedStyle(l).pointerEvents === 'stroke'; });
            if (!dh) return null;
            const r = dh.getBoundingClientRect();
            return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
        }"""
    )


def _open_editor(gm_page: Page, mid: int) -> None:
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
    expect(gm_page.locator("#me-overlay")).to_be_visible()
    gm_page.wait_for_timeout(300)
    me_clear_toolbar(gm_page)


def test_double_click_wall_arms_move_and_resize(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": [
            {"id": "w", "x1": 200, "y1": 320, "x2": 700, "y2": 320, "style": "stone"}]})
        try:
            _open_editor(gm_page, mid)
            assert not _handles(gm_page)  # nothing selected yet
            wc = _wall_hit_center(gm_page)
            assert wc, "no wall hit-line"
            gm_page.mouse.dblclick(wc["x"], wc["y"])
            gm_page.wait_for_timeout(250)
            # Selected → two yellow end-handles (resize) appear.
            assert len(_handles(gm_page)) == 2, _handles(gm_page)
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})


def test_double_click_door_selects_without_opening(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": [
            {"id": "w", "x1": 200, "y1": 320, "x2": 700, "y2": 320, "style": "stone",
             "doors": [{"id": "d1", "t0": 0.4, "t1": 0.6, "open": False}]}]})
        try:
            _open_editor(gm_page, mid)
            dc = _door_hit_center(gm_page)
            assert dc, "no door hit-line"
            gm_page.mouse.dblclick(dc["x"], dc["y"])
            # Wait past the 220ms deferred open-toggle to prove it was cancelled.
            gm_page.wait_for_timeout(500)
            d = c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls").json()["walls"][0]["doors"][0]
            assert d["open"] is False, d  # did NOT open
            # Selected → two yellow edge-handles (resize) appear.
            assert len(_handles(gm_page)) == 2, _handles(gm_page)
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})
