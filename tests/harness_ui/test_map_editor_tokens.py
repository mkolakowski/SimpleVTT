"""v2.777.0 — sample (preview) tokens in the map editor.

The 🎭 Token button drops a draggable, ephemeral token for testing the map.
Tokens are client-side only (never persisted), so this asserts on the DOM.
"""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def _open_editor(gm_page):
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
    expect(gm_page.locator("#me-overlay")).to_be_visible()
    gm_page.wait_for_timeout(400)


def test_token_button_places_multiple(gm_page: Page) -> None:
    errors: list[str] = []
    gm_page.on("pageerror", lambda e: errors.append(str(e)))
    _open_editor(gm_page)
    gm_page.locator("#me-token-btn").click()
    gm_page.locator("#me-token-btn").click()
    expect(gm_page.locator(".me-token")).to_have_count(2)
    assert not errors, f"JS errors: {errors}"


def test_token_drags(gm_page: Page) -> None:
    _open_editor(gm_page)
    # One token so the drag can't accidentally grab an overlapping neighbour.
    gm_page.locator("#me-token-btn").click()
    expect(gm_page.locator(".me-token")).to_have_count(1)
    box = gm_page.locator(".me-token").first.bounding_box()
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    gm_page.mouse.move(cx, cy)
    gm_page.mouse.down()
    gm_page.mouse.move(cx + 140, cy + 90, steps=6)
    gm_page.mouse.up()
    gm_page.wait_for_timeout(150)
    after = gm_page.locator(".me-token").first.bounding_box()
    assert abs(after["x"] - box["x"]) > 30 or abs(after["y"] - box["y"]) > 30, (box, after)


def test_token_snaps_to_grid(gm_page: Page) -> None:
    _open_editor(gm_page)
    gm_page.locator("#me-token-btn").click()
    expect(gm_page.locator(".me-token")).to_have_count(1)
    box = gm_page.locator(".me-token").first.bounding_box()
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    # Drag to an arbitrary off-grid spot.
    gm_page.mouse.move(cx, cy)
    gm_page.mouse.down()
    gm_page.mouse.move(cx + 97, cy + 53, steps=5)
    gm_page.mouse.up()
    gm_page.wait_for_timeout(150)
    # The token's map coords must land on a grid CELL CENTRE.
    res = gm_page.evaluate("""() => {
        const t = window.__meTokens[0], g = window.__meGrid;
        const fx = (((t.x - g.offX) % g.px) + g.px) % g.px;
        const fy = (((t.y - g.offY) % g.px) + g.px) % g.px;
        return { fx, fy, half: g.px / 2 };
    }""")
    assert abs(res["fx"] - res["half"]) < 0.6, res
    assert abs(res["fy"] - res["half"]) < 0.6, res


def test_token_perspective_toggles(gm_page: Page) -> None:
    _open_editor(gm_page)
    gm_page.locator("#me-token-btn").click()
    tok = gm_page.locator(".me-token").first
    tok.click()  # select → show line of sight (re-targets each click)
    gm_page.wait_for_timeout(150)
    assert gm_page.evaluate("() => window.__meVisionActive") is True
    tok.click()  # click again → clear
    gm_page.wait_for_timeout(150)
    assert gm_page.evaluate("() => window.__meVisionActive") is False


def test_token_perspective_occludes_behind_wall(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        # A full-height wall near the left edge; the centred token sits to its
        # right, so the thin strip left of x=40 is in shadow (can't be seen).
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": [
            {"id": "w", "x1": 40, "y1": 0, "x2": 40, "y2": 5000, "style": "stone"}]})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(400)
            gm_page.locator("#me-token-btn").click()
            box = gm_page.locator(".me-token").first.bounding_box()
            gm_page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            gm_page.wait_for_timeout(200)
            res = gm_page.evaluate("""() => {
                const t = window.__meTokens[0];
                const cx = window.__meVisionCanvas.getContext('2d');
                const a = (x, y) => cx.getImageData(Math.round(x), Math.round(y), 1, 1).data[3];
                return { active: window.__meVisionActive, tx: t.x, ty: t.y,
                         eye: a(t.x, t.y), behind: a(12, t.y) };
            }""")
            assert res["active"] is True, res
            assert res["tx"] > 40, res                 # token is right of the wall
            assert res["eye"] < 40, res                # the token's square is visible
            assert res["behind"] > 150, res            # strip behind the wall is veiled
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})


def test_token_darkvision_limits_dark_sight(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})
        c.post(f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/ambient_light",
               json={"ambient_light": "dark"})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(400)
            gm_page.locator("#me-token-btn").click()
            tok = gm_page.locator(".me-token").first
            tok.click()  # show line of sight (re-targets the token each time)

            def eye_alpha():
                return gm_page.evaluate("""() => {
                    const t = window.__meTokens[0];
                    const g = window.__meVisionCanvas.getContext('2d');
                    return { dark: window.__meVisionDark,
                             eye: g.getImageData(t.x, t.y, 1, 1).data[3] };
                }""")

            # Darkvision: None → blind in the dark; the token's own square is veiled.
            tok.click(button="right")
            gm_page.locator("#me-ctx-menu button", has_text="None").click()
            gm_page.wait_for_timeout(150)
            r0 = eye_alpha()
            assert r0["dark"] == 0, r0
            assert r0["eye"] > 150, r0

            # Darkvision: 60 ft → it can now see (a lit bubble at its position).
            tok.click(button="right")
            gm_page.locator("#me-ctx-menu button", has_text="60 ft").click()
            gm_page.wait_for_timeout(150)
            r60 = eye_alpha()
            assert r60["dark"] == 60, r60
            assert r60["eye"] < 40, r60
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/lights", json={"lights": []})
            c.post(f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/ambient_light",
                   json={"ambient_light": "bright"})


def test_two_token_buttons_and_active_ring(gm_page: Page) -> None:
    # v2.785.2 — two coloured token buttons; left-clicking a token shows its
    # perspective and rings it as the active vantage.
    _open_editor(gm_page)
    gm_page.locator("#me-token-btn").click()    # blue
    gm_page.locator("#me-token2-btn").click()   # orange
    expect(gm_page.locator(".me-token")).to_have_count(2)
    fills = set(gm_page.eval_on_selector_all(
        '.me-token circle[stroke="#fff"]',
        "els => els.map(e => e.getAttribute('fill'))"))
    assert fills == {"#5096ff", "#ff9b42"}, fills
    # Left-click one → perspective active + a ring marks it.
    tok = gm_page.locator(".me-token").first
    tok.click()
    expect(gm_page.locator(".me-token--active")).to_have_count(1)
    assert gm_page.evaluate("() => window.__meVisionActive") is True
    tok.click()  # toggle off
    expect(gm_page.locator(".me-token--active")).to_have_count(0)


def test_token_right_click_remove(gm_page: Page) -> None:
    _open_editor(gm_page)
    gm_page.locator("#me-token-btn").click()
    expect(gm_page.locator(".me-token")).to_have_count(1)
    tok = gm_page.locator(".me-token").first
    box = tok.bounding_box()
    gm_page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2,
                        button="right")
    gm_page.locator("#me-ctx-menu button", has_text="Remove").click()
    gm_page.wait_for_timeout(150)
    expect(gm_page.locator(".me-token")).to_have_count(0)
