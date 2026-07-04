"""v2.890.0 — per-region "hide from players" flag on terrain regions.

A terrain region may carry ``hidden: true``; it round-trips through the
terrain PUT/GET and is drawn only for the GM on the tabletop (the render-side
behaviour is covered by tests/harness_ui/test_terrain_hidden_player.py).
"""
from __future__ import annotations

import httpx

BASE_URL = "http://localhost:8013"
CAMPAIGN_ID = 1


def test_terrain_hidden_flag_roundtrips():
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/terrain", json={"terrain": [
            {"id": "hid", "x": 100, "y": 100, "w": 70, "h": 70, "type": "lava", "hidden": True},
            {"id": "vis", "x": 300, "y": 100, "w": 70, "h": 70, "type": "water"},
        ]})
        try:
            t = c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/terrain").json()["terrain"]
            by_id = {r["id"]: r for r in t}
            assert by_id["hid"].get("hidden") is True, by_id["hid"]
            # A region without the flag stays lean (no falsey key stored).
            assert "hidden" not in by_id["vis"], by_id["vis"]
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/terrain", json={"terrain": []})
