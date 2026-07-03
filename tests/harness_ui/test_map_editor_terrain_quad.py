"""v2.848.0 — free-form (four-corner) terrain quads on gridless maps.

On a gridless map the terrain tool places a free-form quadrilateral by clicking
four dots; the saved region carries `points` (4 corner pairs) with x/y/w/h as
its bounding box. In Resize mode each corner handle drags independently (only
that corner moves). The map's grid_type is flipped to "none" for the test and
restored to "square" after (the flagship is the harness's square anchor).
"""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def _terrain(c, mid):
    return c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/terrain").json()["terrain"]


def test_four_dot_quad_placement_and_corner_drag(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.post(f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/grid_type",
               json={"grid_type": "none"})
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/terrain", json={"terrain": []})
        # Clear the seeded walls for the duration: wall <line>s render above the
        # terrain corner-handles and would swallow the handle's pointerdown if a
        # quad corner lands near one (restored verbatim in the finally).
        saved_walls = c.get(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls").json()["walls"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(400)

            # Enter terrain mode, then click four dots (below the floating
            # toolbar). Map-pixel positions vary with the fitted zoom, so
            # click at screen coords over the stage's lower half.
            gm_page.click("#me-terrain-btn")
            box = gm_page.locator("#me-overlay").bounding_box()
            cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] * 0.62
            for dx, dy in [(-120, -60), (130, -80), (110, 90), (-140, 70)]:
                gm_page.mouse.click(cx + dx, cy + dy)
                gm_page.wait_for_timeout(120)
            gm_page.wait_for_timeout(400)

            ts = _terrain(c, mid)
            assert len(ts) == 1, ts
            quad = ts[0]
            assert len(quad.get("points") or []) == 4, quad
            # bbox mirrors the points.
            xs = [p[0] for p in quad["points"]]
            assert quad["x"] == min(xs) and quad["w"] > 6, quad

            # Resize: right-click → Resize → 4 handles; drag one corner and
            # confirm ONLY that corner moved.
            gm_page.locator(".me-terrain").first.dispatch_event("contextmenu")
            gm_page.locator("#me-ctx-menu button", has_text="Resize").click()
            gm_page.wait_for_timeout(150)
            handles = gm_page.locator('#me-overlay circle[fill="#ffd24a"]')
            assert handles.count() == 4, handles.count()

            before = [list(p) for p in quad["points"]]
            h0 = handles.nth(0).bounding_box()
            hx, hy = h0["x"] + h0["width"] / 2, h0["y"] + h0["height"] / 2
            gm_page.mouse.move(hx, hy)
            gm_page.mouse.down()
            gm_page.mouse.move(hx - 60, hy - 40, steps=8)
            gm_page.mouse.up()
            gm_page.wait_for_timeout(400)

            after = _terrain(c, mid)[0]["points"]
            moved = [i for i in range(4) if after[i] != before[i]]
            assert moved == [0], (before, after)   # only the dragged corner
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/terrain", json={"terrain": []})
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls",
                  json={"walls": saved_walls})
            c.post(f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/grid_type",
                   json={"grid_type": "square"})
