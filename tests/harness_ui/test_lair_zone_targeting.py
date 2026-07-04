"""v2.872.0 — zone-driven lair-action targeting.

When a lair action is triggered, if a placed lair zone is bound to that action
(its `actions` list contains the id), the tokens inside the zone become the
AoE targets automatically — no manual target picking. `_lairZoneTargetsForAction`
does the geometry (token centre inside the zone) + resolves each token to its
combatant id (via `source_token_id`), falling back to `tok:<id>`. It returns
`null` when no zone is bound (→ the trigger falls back to the manual picker).
"""
from __future__ import annotations

import json

import httpx
from playwright.sync_api import Page

from .conftest import BASE_URL, CAMPAIGN_ID


def test_zone_targets_resolve_tokens_inside(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        toks = c.get(f"/api/campaign/{CAMPAIGN_ID}/tokens").json()["tokens"]
        t = toks[0]
        tid, tx, ty = t["id"], float(t["x"]), float(t["y"])
        # A zone whose rect surrounds this token's cell centre, bound to a
        # test action id.
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lair_zones", json={"lair_zones": [
            {"id": "zt", "x": tx - 90, "y": ty - 90, "w": 300, "h": 300,
             "label": "Blast", "actions": ["zone-action-x"]},
        ]})
        battle = {
            "combatants": [{
                "id": "cbtInZone", "source_token_id": tid, "name": "In Zone",
                "initiative": 20, "hp_current": 10, "hp_max": 10, "buffs": [],
                "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
            }],
            "turn_index": 0, "round": 1, "active": True,
        }
    try:
        gm_page.add_init_script(
            f"window.localStorage.setItem('simplevtt_battle_{CAMPAIGN_ID}', "
            f"{json.dumps(json.dumps(battle))});")
        gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
        gm_page.wait_for_selector("#wall-overlay", timeout=8000)
        gm_page.wait_for_timeout(800)

        # A zone IS bound to this action → the token inside resolves to its
        # combatant id.
        res = gm_page.evaluate("() => window._lairZoneTargetsForAction('zone-action-x')")
        assert res is not None, "a bound action should return a target set"
        assert "cbtInZone" in res["ids"], res
        assert res["zones"] and res["zones"][0]["label"] == "Blast", res

        # No zone bound to this action → null (the trigger falls back to the
        # manual target picker).
        none = gm_page.evaluate("() => window._lairZoneTargetsForAction('unbound-action')")
        assert none is None, none
    finally:
        with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
            c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lair_zones",
                  json={"lair_zones": []})
