"""v2.766.0 — fog of war on the player tabletop.

With fog enabled + a revealed rectangle, a non-GM player's fog overlay is
opaque over the hidden area and cleared inside the revealed rect. Sampled via
`window.__fogCanvasForTest` (pure map-pixel coords).
"""
from __future__ import annotations

import httpx
from playwright.sync_api import Page

from .conftest import BASE_URL, CAMPAIGN_ID


def test_player_fog_obscures_unrevealed(alice_page: Page) -> None:
    errors: list[str] = []
    alice_page.on("pageerror", lambda e: errors.append(str(e)))
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/fog",
              json={"enabled": True,
                    "revealed": [{"x": 300, "y": 300, "w": 250, "h": 250}]})
        try:
            alice_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
            alice_page.wait_for_function(
                "() => window.__fogCanvasForTest", timeout=8000)
            alice_page.wait_for_timeout(1000)  # fog bootstrap from /active-map

            res = alice_page.evaluate("""() => {
                const cx = window.__fogCanvasForTest.getContext('2d');
                const a = (x, y) => cx.getImageData(x, y, 1, 1).data[3];
                return { inside: a(420, 420), outside: a(60, 60) };
            }""")
            # Revealed area cleared; hidden area heavily veiled (player view).
            assert res["inside"] < 40, res
            assert res["outside"] > 200, res
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/fog",
                  json={"enabled": False, "revealed": []})

    assert not errors, f"JS errors: {errors}"
