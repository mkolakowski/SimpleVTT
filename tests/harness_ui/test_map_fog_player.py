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


def test_player_fog_reveals_only_own_tokens_vision(alice_page: Page) -> None:
    """v2.945.0 — a player sees only through the tokens they OWN, not the whole
    party. A token alice controls reveals its cell; a token she doesn't control
    (far away) does not add its cell to her view."""
    alice_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
    alice_page.wait_for_function(
        "() => window.__testDrawFog && window.__gridSizeForTest && window.ME", timeout=8000)
    alice_page.wait_for_timeout(300)

    res = alice_page.evaluate(
        """() => {
            const myId = window.ME.id;
            const owned = { id: 90501, x: 100, y: 100, size: 1, controller_user_id: myId };
            // Far enough that owned's 60ft sight can't reach the other's cell.
            const other = { id: 90502, x: 1400, y: 1000, size: 1,
                            controller_user_id: myId + 99999, character_id: null };
            const r = window.__testDrawFog({ tokens: [owned, other], walls: [], explored: [] });
            const g = window.__gridSizeForTest();
            const cell = (t) => Math.floor((t.x + g / 2) / g) + ',' + Math.floor((t.y + g / 2) / g);
            const vis = new Set(r.visible);
            return { isGm: !!window.ME.isGm, ownedVisible: vis.has(cell(owned)),
                     otherVisible: vis.has(cell(other)), n: r.visible.length };
        }"""
    )
    assert res["isGm"] is False, res
    assert res["ownedVisible"] is True, res       # her own token reveals its cell
    assert res["otherVisible"] is False, res      # a non-owned token adds nothing
