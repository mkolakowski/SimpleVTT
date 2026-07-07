"""v2.949.0 — parse-vs-fetch race recovery for the map bootstrap ("Load-Bearing").

tabletop.html's load() fetches /active-map and pushes walls/lights/fog into
tabletop.js via window._setMap*. If that fetch resolved before tabletop.js
parsed, those calls were dropped (their guards no-op when the setters are
undefined), leaving vision/lighting/fog on EMPTY walls until the next
walls_update WS — which is why toggling a door "fixed" a GM's targeted-token
perspective that was seeing past walls on load.

tabletop.html now buffers the bootstrap (`window.__ttMapBootstrap`) and
tabletop.js re-applies it on init (`window.__reapplyMapBootstrap`). This test
drives the failure directly (drop the walls) and asserts the buffer recovery
restores wall occlusion in the targeted-token POV veil.
"""
from __future__ import annotations

import httpx
from playwright.sync_api import Page

from .conftest import BASE_URL


def _goblin_warrens_cid(c: httpx.Client) -> int:
    return next(x["id"] for x in c.get("/api/user/gm-campaigns").json()
               if "Goblin Warrens" in x["name"])


def test_wall_bootstrap_buffer_recovers_dropped_walls(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as gm:
        gm.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        cid = _goblin_warrens_cid(gm)
        tok = gm.post(f"/api/campaign/{cid}/tokens",
                      json={"label": "POV", "x": 700, "y": 900}).json()
        tid = tok["id"]
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{cid}")
            gm_page.wait_for_selector("#token-veil-canvas", timeout=10000)
            gm_page.wait_for_timeout(1200)

            res = gm_page.evaluate(
                """(tid) => {
                    const a = (x, y) => {
                        const cv = window.__visionVeilForTest;
                        return cv ? cv.getContext('2d').getImageData(x, y, 1, 1).data[3] : -1;
                    };
                    // Adopt the token's POV. Sample a point behind the fence but
                    // inside its darkvision reach: veiled iff the wall occludes.
                    window._targetingState.setTarget(tid);
                    const withWalls = a(735, 350);
                    // Reproduce the race outcome: the walls push was dropped.
                    window._setMapWalls([]);
                    const noWalls = a(735, 350);
                    // Recovery: re-apply the buffered bootstrap (init does this).
                    const recovered = window.__reapplyMapBootstrap();
                    const afterRecover = a(735, 350);
                    return { hasBuffer: !!window.__ttMapBootstrap,
                             withWalls, noWalls, recovered, afterRecover };
                }""",
                tid,
            )
            assert res["hasBuffer"] is True, res
            # Wall occludes the point behind the fence → veiled.
            assert res["withWalls"] > 150, res
            # Dropped walls → the darkvision disk reaches past the fence (the bug).
            assert res["noWalls"] < 60, res
            # The buffer re-apply restores wall occlusion.
            assert res["recovered"] is True, res
            assert res["afterRecover"] > 150, res
        finally:
            gm.request("DELETE", f"/api/campaign/{cid}/tokens/{tid}")
