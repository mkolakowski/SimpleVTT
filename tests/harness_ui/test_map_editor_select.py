"""v2.806.0 — marquee multi-select: select, group-move, and group-delete."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID

# Map → screen via the overlay's live CTM, so the test is independent of the
# editor's zoom / grid-snap.
_MAP_TO_SCREEN = """([mx, my]) => {
  const svg = document.getElementById('me-overlay');
  const m = svg.getScreenCTM();
  return [m.a * mx + m.c * my + m.e, m.b * mx + m.d * my + m.f];
}"""


def _props(c, mid):
    return c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/props").json()["props"]


def test_marquee_select_move_delete(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        # Seed two well-separated props so they load with the editor.
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/props", json={"props": [
            {"x": 300, "y": 300, "kind": "🌲"},
            {"x": 420, "y": 300, "kind": "🪑"}]})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(400)

            def scr(mx, my):
                return gm_page.evaluate(_MAP_TO_SCREEN, [mx, my])

            gm_page.locator("#me-select-btn").click()
            # Marquee a box (map 250,250 → 470,360) around both props.
            a, b = scr(250, 250), scr(470, 360)
            gm_page.mouse.move(a[0], a[1])
            gm_page.mouse.down()
            gm_page.mouse.move(b[0], b[1], steps=6)
            gm_page.mouse.up()
            gm_page.wait_for_timeout(200)
            rings = gm_page.eval_on_selector_all(
                "#me-overlay circle",
                "els => els.filter(e => e.getAttribute('stroke') === '#6cf').length")
            assert rings >= 2, rings

            # Drag from inside the selection (map 360,300 → 360,440) to move both.
            s, e = scr(360, 300), scr(360, 440)
            gm_page.mouse.move(s[0], s[1])
            gm_page.mouse.down()
            gm_page.mouse.move(e[0], e[1], steps=6)
            gm_page.mouse.up()
            gm_page.wait_for_timeout(300)
            moved = _props(c, mid)
            assert all(p["y"] > 320 for p in moved), moved  # shifted well below 300

            gm_page.keyboard.press("Delete")
            gm_page.wait_for_timeout(300)
            assert len(_props(c, mid)) == 0
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/props", json={"props": []})
