"""v2.948.0 — light glow is hidden behind the fog of war ("Snuffed").

The #light-glow-canvas (colored torch glow, z-7) sits above the fog veil, so it
would otherwise shine through unexplored fog. tabletop.js's drawFog exposes its
fog veil as ``window._glowFogMask``; the glow loop erases itself by that mask,
so a torch the player can't see (behind fog / past a wall) stops glowing.

On the fog-ON Goblin Warrens, a token alice owns below the closed-gate fence
sees the hearth beside it but not the tunnel torches above the wall — so the
fog mask is opaque over a tunnel torch (its glow erased) and clear at the hearth.
"""
from __future__ import annotations

import httpx
from playwright.sync_api import Page

from .conftest import BASE_URL


def _goblin_warrens_cid(c: httpx.Client) -> int:
    return next(x["id"] for x in c.get("/api/user/gm-campaigns").json()
               if "Goblin Warrens" in x["name"])


def test_light_glow_hidden_behind_fog_for_player(alice_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as gm:
        gm.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        cid = _goblin_warrens_cid(gm)
        am = gm.get(f"/api/campaign/{cid}/active-map").json()
        lights = am["lights"]
        # Hearth (big, beside the party) → visible; a tunnel torch up top behind
        # the fence → fogged.
        hearth = next(l for l in lights if l["dim_ft"] >= 50)
        torch = next(l for l in lights if l["dim_ft"] <= 12 and l["y"] < 300)
        tok = gm.post(f"/api/campaign/{cid}/tokens",
                      json={"label": "AlicePC", "x": 700, "y": 900}).json()
        tid = tok["id"]
        try:
            alice_page.goto(f"{BASE_URL}/campaign/{cid}")
            alice_page.wait_for_selector("#token-veil-canvas", timeout=10000)
            alice_id = alice_page.evaluate("() => window.ME.id")
            r = gm.patch(f"/api/campaign/{cid}/token/{tid}",
                         json={"controller_user_id": alice_id})
            assert r.status_code == 200, r.text
            alice_page.reload()
            alice_page.wait_for_selector("#light-glow-canvas", timeout=10000)
            alice_page.wait_for_timeout(1400)  # let fog compute + the glow loop run

            res = alice_page.evaluate(
                """([hx, hy, tx, ty]) => {
                    if (window._renderCanvas) window._renderCanvas();
                    const fm = window._glowFogMask;
                    const glow = document.getElementById('light-glow-canvas');
                    const gctx = glow.getContext('2d');
                    const ga = (x, y) => gctx.getImageData(Math.round(x), Math.round(y), 1, 1).data[3];
                    const ma = (x, y) => fm
                        ? fm.getContext('2d').getImageData(Math.round(x), Math.round(y), 1, 1).data[3]
                        : -1;
                    return {
                        maskPresent: !!fm,
                        maskAtTorch: ma(tx, ty), maskAtHearth: ma(hx, hy),
                        glowAtTorch: ga(tx, ty), glowAtHearth: ga(hx, hy),
                    };
                }""",
                [hearth["x"], hearth["y"], torch["x"], torch["y"]],
            )
            # The fog veil is exposed and opaque over the hidden tunnel torch,
            # clear beside the party's hearth.
            assert res["maskPresent"] is True, res
            assert res["maskAtTorch"] > 150, res
            assert res["maskAtHearth"] < 90, res
            # …so the tunnel torch's glow is erased while the hearth still glows.
            assert res["glowAtTorch"] < 12, res
            assert res["glowAtHearth"] > res["glowAtTorch"], res
        finally:
            gm.request("DELETE", f"/api/campaign/{cid}/tokens/{tid}")
