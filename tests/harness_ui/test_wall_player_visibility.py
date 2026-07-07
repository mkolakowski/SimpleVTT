"""v2.950.0 — walls/doors are visible to players only where they can see.

The #wall-overlay moved above the veil (z-8). For a player on a fog-enabled map
tabletop.js CSS-masks it by the fog veil, so walls appear only in the party's
visible/explored area and stay hidden beyond fog. The GM (no fog veil) sees every
wall with no mask.
"""
from __future__ import annotations

import httpx
from playwright.sync_api import Page

from .conftest import BASE_URL


def _goblin_warrens_cid(c: httpx.Client) -> int:
    return next(x["id"] for x in c.get("/api/user/gm-campaigns").json()
               if "Goblin Warrens" in x["name"])


def test_wall_overlay_is_fog_masked_for_player(alice_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as gm:
        gm.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        cid = _goblin_warrens_cid(gm)
    alice_page.goto(f"{BASE_URL}/campaign/{cid}")
    alice_page.wait_for_selector("#wall-overlay", timeout=10000)
    alice_page.wait_for_timeout(1200)  # fog compute + a render

    r = alice_page.evaluate(
        """() => {
            const wo = document.getElementById('wall-overlay');
            const cs = getComputedStyle(wo);
            const mask = wo.style.maskImage || wo.style.webkitMaskImage || cs.maskImage || '';
            return { isGm: !!window.ME.isGm, z: cs.zIndex, mask,
                     children: wo.childElementCount };
        }"""
    )
    assert r["isGm"] is False, r
    assert r["z"] == "8", r                     # above the veil
    assert r["children"] > 0, r                 # walls actually render for the player
    assert "url(" in r["mask"], r               # …and are fog-masked (only where seen)


def test_wall_overlay_not_masked_for_gm(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as gm:
        gm.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        cid = _goblin_warrens_cid(gm)
    gm_page.goto(f"{BASE_URL}/campaign/{cid}")
    gm_page.wait_for_selector("#wall-overlay", timeout=10000)
    gm_page.wait_for_timeout(1200)

    r = gm_page.evaluate(
        """() => {
            const wo = document.getElementById('wall-overlay');
            const mask = wo.style.maskImage || wo.style.webkitMaskImage || '';
            return { isGm: !!window.ME.isGm, z: getComputedStyle(wo).zIndex, mask };
        }"""
    )
    assert r["isGm"] is True, r
    assert r["z"] == "8", r
    assert "url(" not in r["mask"], r           # GM sees every wall (no fog mask)


def test_wall_mask_full_opacity_where_player_has_seen(alice_page: Page) -> None:
    """v2.952.1 — walls render at FULL opacity where the player has explored/can
    see (the old veil-derived mask left explored walls at ~40%)."""
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as gm:
        gm.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        cid = _goblin_warrens_cid(gm)
        tok = gm.post(f"/api/campaign/{cid}/tokens",
                      json={"label": "Scout", "x": 700, "y": 760}).json()
        tid = tok["id"]
        try:
            alice_page.goto(f"{BASE_URL}/campaign/{cid}")
            alice_page.wait_for_selector("#wall-overlay", timeout=10000)
            aid = alice_page.evaluate("() => window.ME.id")
            r = gm.patch(f"/api/campaign/{cid}/token/{tid}",
                         json={"controller_user_id": aid})
            assert r.status_code == 200, r.text
            alice_page.reload()
            alice_page.wait_for_function("() => window.__wallMaskForTest && window.__gridSizeForTest",
                                         timeout=10000)
            alice_page.wait_for_timeout(1500)
            r = alice_page.evaluate(
                """() => {
                    const m = window.__wallMaskForTest;
                    const a = (x, y) => m.getContext('2d')
                        .getImageData(Math.round(x), Math.round(y), 1, 1).data[3];
                    return { atToken: a(735, 795) };  // the scout's own cell → seen
                }"""
            )
            # Full-opacity reveal where the player has seen (not ~99/255).
            assert r["atToken"] == 255, r
        finally:
            gm.request("DELETE", f"/api/campaign/{cid}/tokens/{tid}")
