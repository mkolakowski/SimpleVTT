"""v2.951.0 — live movement ruler while dragging a token on a gridless map.

Players and the GM see a ruler (line + distance in ft) from the token's start to
the cursor WHILE dragging, so they know how far the move is before dropping. It's
gridless-only (square/hex maps convey distance via cells) and shows the token's
speed budget when it's the active combatant.
"""
from __future__ import annotations

import httpx
from playwright.sync_api import Page

from .conftest import BASE_URL


def _goblin_warrens_cid(c: httpx.Client) -> int:
    return next(x["id"] for x in c.get("/api/user/gm-campaigns").json()
               if "Goblin Warrens" in x["name"])


def test_gridless_drag_ruler_distance_and_render(alice_page: Page) -> None:
    # The Goblin Warrens is gridless (grid_size_px 70).
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as gm:
        gm.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        cid = _goblin_warrens_cid(gm)
    alice_page.goto(f"{BASE_URL}/campaign/{cid}")
    alice_page.wait_for_function("() => window.__dragRulerTest", timeout=10000)
    alice_page.wait_for_timeout(400)

    r = alice_page.evaluate(
        """() => {
            const D = window.__dragRulerTest;
            // 700px on a 70px (=5 ft) gridless map → 10 cells → 50 ft, euclidean.
            const m = D.compute(100, 100, 800, 100, { id: 999999 });
            // Drive the live ruler, then sample the veil canvas along the line.
            D.set({ origX: 100, origY: 100, x: 800, y: 100, token: { id: 999999 } });
            const veil = document.getElementById('token-veil-canvas');
            const sh = parseInt(veil.dataset.stripH || '0', 10);
            const vc = veil.getContext('2d');
            const half = window.__gridSizeForTest ? window.__gridSizeForTest() / 2 : 35;
            // Midpoint of the line, in canvas pixels (+ strip offset).
            const px = (mx, my) => vc.getImageData(Math.round(mx + sh), Math.round(my + sh), 1, 1).data;
            const onLine = px(450 + half, 100 + half);
            D.clear();
            const cleared = px(450 + half, 100 + half);
            return {
                gridless: m.gridless, ft: m.ft, cap: m.cap,
                onLineAlpha: onLine[3], onLineR: onLine[0], onLineG: onLine[1],
                clearedAlpha: cleared[3],
            };
        }"""
    )
    assert r["gridless"] is True, r
    assert abs(r["ft"] - 50.0) < 0.5, r                # 700px → 50 ft
    assert r["cap"] is None, r                          # not the active combatant → no cap
    # The ruler paints an amber line on the veil while dragging…
    assert r["onLineAlpha"] > 0, r
    assert r["onLineR"] > 180 and r["onLineG"] > 130, r  # amber-ish stroke
    # …and clears on drop.
    assert r["clearedAlpha"] < r["onLineAlpha"], r
