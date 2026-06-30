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
