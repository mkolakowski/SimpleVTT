"""v2.943.0 — VTT selected-token POV veil ("The Adopted Eye").

Parity with the map editor's darkvision line-of-sight preview: when the GM
targets a token, the VTT veils what that token can't see — a darkvision-reach
disk (dark ambient) minus wall/closed-door shadows — independent of fog of war.
The Goblin Warrens ships fog OFF + a closed gate wall, so a token below the
fence sees the camp near it but is veiled beyond the wall.
"""
from __future__ import annotations

import httpx
from playwright.sync_api import Page

from .conftest import BASE_URL


def _goblin_warrens_cid(c: httpx.Client) -> int:
    return next(x["id"] for x in c.get("/api/user/gm-campaigns").json()
               if "Goblin Warrens" in x["name"])


def test_gm_target_narrows_to_that_tokens_line_of_sight(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        cid = _goblin_warrens_cid(c)
        # A token below the fence wall (fence sits at natural y ~= 600).
        tok = c.post(f"/api/campaign/{cid}/tokens",
                     json={"label": "POV", "x": 700, "y": 900}).json()
        tid = tok["id"]
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{cid}")
            gm_page.wait_for_selector("#token-veil-canvas", timeout=10000)
            gm_page.wait_for_timeout(1200)

            r = gm_page.evaluate(
                """(tid) => {
                    // Adopt the token's POV (real targeting path → triggers render()).
                    window._targetingState.setTarget(tid);
                    const cv = window.__visionVeilForTest;
                    if (!cv) return { err: 'no vision veil canvas' };
                    const px = (x, y) => cv.getContext('2d').getImageData(x, y, 1, 1).data[3];
                    return {
                        nearAlpha: px(735, 935),   // at the token → revealed (clear)
                        farAlpha: px(60, 60),      // above the fence, far → veiled
                    };
                }""",
                tid,
            )
            assert "err" not in r, r
            # The token's own cell is revealed; the far side of the wall is veiled.
            assert r["nearAlpha"] < 40, r
            assert r["farAlpha"] > 150, r
            assert r["farAlpha"] - r["nearAlpha"] > 120, r
        finally:
            c.request("DELETE", f"/api/campaign/{cid}/tokens/{tid}")


def test_player_cannot_see_past_walls_with_fog_off(alice_page: Page) -> None:
    """v2.947.0 — anti-bypass: on a fog-OFF map an UNtargeted player is still
    bounded to their own PCs' line of sight, so they can't see past walls. The
    Goblin Warrens ships fog OFF; a token alice owns below the fence reveals its
    cell but the far side of the closed-gate wall stays veiled."""
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as gm:
        gm.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        cid = _goblin_warrens_cid(gm)
        tok = gm.post(f"/api/campaign/{cid}/tokens",
                      json={"label": "AlicePC", "x": 700, "y": 900}).json()
        tid = tok["id"]
        try:
            alice_page.goto(f"{BASE_URL}/campaign/{cid}")
            alice_page.wait_for_selector("#token-veil-canvas", timeout=10000)
            alice_id = alice_page.evaluate("() => window.ME.id")
            # Give alice control of the token, then reload so her client owns it.
            r = gm.patch(f"/api/campaign/{cid}/token/{tid}",
                         json={"controller_user_id": alice_id})
            assert r.status_code == 200, r.text
            alice_page.reload()
            alice_page.wait_for_selector("#token-veil-canvas", timeout=10000)
            alice_page.wait_for_timeout(1200)

            res = alice_page.evaluate(
                """() => {
                    if (window._renderCanvas) window._renderCanvas();  // no target set
                    const cv = window.__visionVeilForTest;
                    if (!cv) return { err: 'no veil canvas — player view is NOT bounded' };
                    const px = (x, y) => cv.getContext('2d').getImageData(x, y, 1, 1).data[3];
                    return { isGm: !!window.ME.isGm,
                             nearAlpha: px(735, 935), farAlpha: px(60, 60) };
                }"""
            )
            assert "err" not in res, res
            assert res["isGm"] is False, res
            assert res["nearAlpha"] < 40, res    # own token's cell revealed
            assert res["farAlpha"] > 150, res    # past the fence → veiled (no bypass)
        finally:
            gm.request("DELETE", f"/api/campaign/{cid}/tokens/{tid}")
