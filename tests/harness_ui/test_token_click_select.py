"""v2.968.0 — click-to-select a token on the tabletop. A plain click (no drag)
on a token makes it the SELECTED token (window.vttSelectedTokenId), the acting
token for door open-checks; Escape clears it.
"""
from __future__ import annotations

from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def _wait_ready(page: Page) -> None:
    expect(page.locator("#vtt-canvas")).to_be_visible(timeout=8000)
    page.wait_for_function(
        "() => typeof window.vttSelectedTokenId === 'function'", timeout=6000)


def _place(page: Page, char_id: int, x: float, y: float) -> dict:
    return page.evaluate(
        """async ({cid, charId, x, y}) => {
            const r = await fetch('/api/campaign/'+cid+'/character/'+charId+'/place-token', {
                method: 'POST', credentials: 'include',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({x, y})});
            return await r.json();
        }""", {"cid": CAMPAIGN_ID, "charId": char_id, "x": x, "y": y})


def _tok(page: Page, char_id: int) -> dict:
    toks = page.evaluate(
        """async (cid) => {
            const r = await fetch('/api/campaign/'+cid+'/tokens', {credentials:'include'});
            return (await r.json()).tokens || [];
        }""", CAMPAIGN_ID)
    return next(t for t in toks if t.get("character_id") == char_id)


def _canvas_geo(page: Page) -> dict:
    return page.evaluate(
        """() => {
            const c = document.getElementById('vtt-canvas');
            const r = c.getBoundingClientRect();
            return {left: r.x, top: r.y, rw: r.width, offW: c.offsetWidth,
                    strip: +(c.dataset.stripH || 0), grid: +c.dataset.gridSize || 70};
        }""")


def _w2s(geo, wx, wy):
    scale = geo["rw"] / geo["offW"]
    return (geo["left"] + (wx + geo["strip"]) * scale,
            geo["top"] + (wy + geo["strip"]) * scale)


def test_click_selects_token_escape_clears(gm_page: Page, roster: dict) -> None:
    pip = roster["Pip Quickfingers"]
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
    _wait_ready(gm_page)
    _place(gm_page, pip["id"], 280.0, 280.0)
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
    _wait_ready(gm_page)
    tok = _tok(gm_page, pip["id"])

    assert gm_page.evaluate("() => window.vttSelectedTokenId()") is None

    geo = _canvas_geo(gm_page)
    half = geo["grid"] / 2
    cx, cy = _w2s(geo, 280 + half, 280 + half)
    # A plain click (no drag) on the token.
    gm_page.mouse.move(cx, cy)
    gm_page.mouse.down(button="left")
    gm_page.mouse.up(button="left")
    gm_page.wait_for_timeout(200)

    assert gm_page.evaluate("() => window.vttSelectedTokenId()") == tok["id"]
    assert gm_page.evaluate("() => window.vttActingTokenId()") == tok["id"]

    # Escape clears the selection.
    gm_page.keyboard.press("Escape")
    gm_page.wait_for_timeout(150)
    assert gm_page.evaluate("() => window.vttSelectedTokenId()") is None
