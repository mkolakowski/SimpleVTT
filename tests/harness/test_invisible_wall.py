"""v2.909.0 — invisible wall type + per-door material.

A wall may carry ``invisible: true`` (blocks sight like a normal wall but isn't
drawn for players); an embedded door may carry its own ``style`` so a door on an
invisible wall still shows a material. Both round-trip through the walls PUT/GET.
"""
from __future__ import annotations

import httpx

BASE_URL = "http://localhost:8013"
CAMPAIGN_ID = 1


def test_invisible_wall_and_door_style_round_trip():
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": [
            {"id": "iw", "x1": 0, "y1": 0, "x2": 200, "y2": 0, "invisible": True,
             "doors": [{"id": "d", "t0": 0.3, "t1": 0.6, "style": "wood"}]},
            {"id": "plain", "x1": 0, "y1": 100, "x2": 200, "y2": 100},
        ]})
        try:
            walls = c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls").json()["walls"]
            by_id = {w["id"]: w for w in walls}
            assert by_id["iw"].get("invisible") is True, by_id["iw"]
            assert by_id["iw"]["doors"][0].get("style") == "wood", by_id["iw"]
            # A plain wall stays visible (invisible defaults false).
            assert by_id["plain"].get("invisible") is False, by_id["plain"]
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})
