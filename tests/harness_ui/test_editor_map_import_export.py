"""v2.922.0 — the map editor can export the full layout as JSON and import one
back (replacing all placed elements). Lets a layout be shared or baked into the
demo seed."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def _walls(c, mid):
    return c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls").json()["walls"]


def test_export_object_carries_the_layers(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": [
            {"id": "w", "x1": 100, "y1": 100, "x2": 400, "y2": 100, "style": "stone"}]})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(300)
            obj = gm_page.evaluate("() => window.__meExportObject()")
            assert obj["_simplevtt_map_export"] == 1, obj
            assert len(obj["walls"]) == 1 and obj["walls"][0]["id"] == "w", obj
            for k in ("terrain", "lights", "hotspots", "gm_pins", "labels",
                      "props", "lair_zones", "fog", "grid", "ambient_light", "token_scale"):
                assert k in obj, (k, list(obj))
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})


def test_import_replaces_the_layout(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(300)
            payload = {
                "_simplevtt_map_export": 1,
                "grid": {"type": "square", "px": 70, "show": True, "offset_x": 0, "offset_y": 0},
                "ambient_light": "dark",
                "token_scale": 1.0,
                "fog": {"enabled": False, "dynamic": False, "revealed": []},
                "walls": [
                    {"id": "iw1", "x1": 50, "y1": 60, "x2": 500, "y2": 60, "style": "cave"},
                    {"id": "iw2", "x1": 50, "y1": 60, "x2": 50, "y2": 400,
                     "window": True, "opacity": 0, "style": "stone"},
                ],
                "terrain": [], "lights": [], "hotspots": [], "gm_pins": [],
                "labels": [], "props": [], "lair_zones": [],
            }
            ok = gm_page.evaluate("(d) => window.__meImportMap(d)", payload)
            assert ok is True
            gm_page.wait_for_timeout(700)
            ws = _walls(c, mid)
            assert len(ws) == 2, ws
            win = next(w for w in ws if w["id"] == "iw2")
            assert win["window"] is True and win["opacity"] == 0, win
            # Ambient persisted too.
            am = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()
            assert am["ambient_light"] == "dark", am
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})
            c.post(f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/ambient_light",
                   json={"ambient_light": "bright"})
