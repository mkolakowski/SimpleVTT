"""v2.955.0 — a gate's two door leaves swing in opposite rotational senses, so
their SVG swing arcs must use opposite sweep flags (both were 1, so one leaf's
arc bulged the wrong way — it didn't reflect the door's opening direction).
"""
from __future__ import annotations

import re

import httpx
from playwright.sync_api import Page

from .conftest import BASE_URL


def _goblin_warrens_cid(c: httpx.Client) -> int:
    return next(x["id"] for x in c.get("/api/user/gm-campaigns").json()
               if "Goblin Warrens" in x["name"])


def _sweep(d: str) -> int:
    # "M x y A rx ry rot large-arc SWEEP ex ey" → the SWEEP flag.
    m = re.search(r"A [\d.]+ [\d.]+ \d+ \d+ (\d+) ", d)
    assert m, d
    return int(m.group(1))


def test_gate_leaves_swing_opposite_directions(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as gm:
        gm.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        cid = _goblin_warrens_cid(gm)
        mid = gm.get(f"/api/campaign/{cid}/active-map").json()["map_id"]
        walls = gm.get(f"/api/campaign/{cid}/active-map").json()["walls"]
        for w in walls:
            for dr in (w.get("doors") or []):
                dr["open"] = True                       # open the gate to draw swing arcs
        gm.put(f"/api/campaign/{cid}/map/{mid}/walls", json={"walls": walls})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{cid}")
            gm_page.wait_for_selector("#wall-overlay", timeout=10000)
            gm_page.wait_for_timeout(800)
            arcs = gm_page.evaluate(
                """() => [...document.getElementById('wall-overlay').querySelectorAll('path')]
                    .map(p => p.getAttribute('d')).filter(d => d && d.includes(' A '))"""
            )
            assert len(arcs) == 2, arcs                  # one swing arc per gate leaf
            sweeps = sorted(_sweep(d) for d in arcs)
            assert sweeps == [0, 1], (sweeps, arcs)      # opposite senses, not [1, 1]
        finally:
            for w in walls:
                for dr in (w.get("doors") or []):
                    dr["open"] = False
            gm.put(f"/api/campaign/{cid}/map/{mid}/walls", json={"walls": walls})
