"""v2.959.0 — OA hard-block backstop on the direct /token/move path.

The pre-move OA preview (``/preview_move``) is best-effort: if it fails, races,
or is skipped, an OA-provoking move reaches the plain ``postMove()`` fallthrough
and the server 409s ``oa_confirmation_required``. Before this fix the fetch
result was ignored, so the token stayed visually moved while the server rejected
it — a silent desync that reads as "the OA didn't stop me". Now ``postMove()``
catches that 409, snaps the token back, and surfaces the same Continue/Stop
modal — the block is real on every path.

We force the backstop by stubbing ``/preview_move`` to report **no OA** while
the real ``/token/move`` still 409s from the server, then assert the OA modal
appears anyway and Stop snaps the token back.
"""
from __future__ import annotations

from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def _wait_ready(page: Page) -> None:
    expect(page.locator("#vtt-canvas")).to_be_visible(timeout=8000)
    page.wait_for_function(
        "() => typeof window.vttGetCharacters === 'function'", timeout=5000)


def _place_token(page: Page, char_id: int, x: float, y: float) -> dict:
    return page.evaluate(
        """async ({cid, charId, x, y}) => {
            const r = await fetch('/api/campaign/'+cid+'/character/'+charId+'/place-token', {
                method: 'POST', credentials: 'include',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({x, y}),
            });
            return await r.json();
        }""",
        {"cid": CAMPAIGN_ID, "charId": char_id, "x": x, "y": y})


def _token_for_char(page: Page, char_id: int) -> dict | None:
    tokens = page.evaluate(
        """async (cid) => {
            const r = await fetch('/api/campaign/'+cid+'/tokens', {credentials:'include'});
            return (await r.json()).tokens || [];
        }""", CAMPAIGN_ID)
    return next((t for t in tokens if t.get("character_id") == char_id), None)


def _seed_battle(page: Page, combatants: list[dict], turn_index: int = 0) -> None:
    payload = {"combatants": combatants, "turn_index": turn_index,
               "round": 1, "active": True}
    page.evaluate(
        """async ({cid, payload}) => {
            await fetch('/api/campaign/'+cid+'/battle', {
                method: 'PUT', credentials: 'include',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload),
            });
            document.dispatchEvent(new CustomEvent('vtt:ws-message', {detail: {
                type: 'battle_update', force_gm_sync: true, data: payload,
            }}));
        }""", {"cid": CAMPAIGN_ID, "payload": payload})


def _clear_battle_server(page: Page) -> None:
    page.evaluate(
        """async (cid) => {
            await fetch('/api/campaign/'+cid+'/battle', {
                method: 'PUT', credentials: 'include',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({combatants: [], round: 0, turn_index: 0, active: false}),
            });
        }""", CAMPAIGN_ID)


def _stub_preview_no_oa(page: Page) -> None:
    """Make /preview_move report NO OA so the client falls through to the
    direct postMove() — the exact condition the backstop guards."""
    page.evaluate(
        """() => {
            const orig = window.fetch;
            window.__origFetch = orig;
            window.fetch = function(url, opts) {
                if (typeof url === 'string' && url.includes('/preview_move')) {
                    return Promise.resolve(new Response(JSON.stringify({
                        would_trigger_oa: false, distance_ft: 15,
                        over_range: false, token_speed_ft: 25,
                    }), {status: 200, headers: {'Content-Type': 'application/json'}}));
                }
                return orig.apply(this, arguments);
            };
        }""")


def _canvas_geo(page: Page) -> dict:
    return page.evaluate(
        """() => {
            const c = document.getElementById('vtt-canvas');
            const r = c.getBoundingClientRect();
            return {left: r.x, top: r.y, rw: r.width, offW: c.offsetWidth,
                    strip: +(c.dataset.stripH || 0), grid: +c.dataset.gridSize || 70};
        }""")


def _world_to_screen(geo: dict, wx: float, wy: float) -> tuple[float, float]:
    scale = geo["rw"] / geo["offW"]
    return (geo["left"] + (wx + geo["strip"]) * scale,
            geo["top"] + (wy + geo["strip"]) * scale)


def _drag(page: Page, s: tuple[float, float], e: tuple[float, float]) -> None:
    page.mouse.move(*s)
    page.mouse.down(button="left")
    page.mouse.move(s[0] + (e[0] - s[0]) * 0.33, s[1] + (e[1] - s[1]) * 0.33)
    page.mouse.move(s[0] + (e[0] - s[0]) * 0.66, s[1] + (e[1] - s[1]) * 0.66)
    page.mouse.move(*e)
    page.mouse.up(button="left")


def test_oa_backstop_when_preview_misses(gm_page: Page, roster: dict) -> None:
    """Preview stubbed to say "no OA"; Pip (active, 25 ft speed) drags 15 ft
    south out of Krieger's 5 ft reach (within cap → no Dash/overrun modal).
    The server 409s, the backstop shows the OA modal, and Stop snaps back."""
    pip = roster["Pip Quickfingers"]
    krieger = roster["Krieger Stonefist"]
    errs: list[str] = []
    gm_page.on("pageerror", lambda e: errs.append(str(e)))

    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
    _wait_ready(gm_page)
    # Pip (mover) at (280,280); Krieger (watcher) one cell NORTH (5 ft).
    _place_token(gm_page, pip["id"], 280.0, 280.0)
    _place_token(gm_page, krieger["id"], 280.0, 210.0)
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
    _wait_ready(gm_page)

    pip_tok = _token_for_char(gm_page, pip["id"])
    kr_tok = _token_for_char(gm_page, krieger["id"])
    assert pip_tok and kr_tok

    try:
        # Truthy `initiative` (not the `init` alias) so the GM init tracker
        # skips its "🎲 Prompt" branch — that inline-script branch references
        # a tabletop.js-scoped `charById` and throws a (pre-existing,
        # unrelated) ReferenceError we don't want polluting the error assert.
        _seed_battle(gm_page, [
            {"char_id": pip["id"], "name": pip["name"], "initiative": 20,
             "speed_walk": 25, "id": "pip-1", "source_token_id": pip_tok["id"],
             "economy": {"action": False, "bonus": False, "reaction": False,
                         "movement": 0, "dash_bonus_ft": 0}},
            {"char_id": krieger["id"], "name": krieger["name"], "initiative": 10,
             "speed_walk": 30, "id": "kr-1", "source_token_id": kr_tok["id"],
             "economy": {"action": False, "bonus": False, "reaction": False,
                         "movement": 0, "dash_bonus_ft": 0}},
        ], turn_index=0)
        _stub_preview_no_oa(gm_page)

        geo = _canvas_geo(gm_page)
        half = geo["grid"] / 2
        start = _world_to_screen(geo, 280 + half, 280 + half)
        # 15 ft (3 cells) SOUTH — within Pip's 25 ft cap so no Dash/overrun
        # modal fires; the only thing that can stop it is the OA backstop.
        end = _world_to_screen(geo, 280 + half, 280 + half + geo["grid"] * 3)
        _drag(gm_page, start, end)

        oa = gm_page.locator('div[role="dialog"][aria-label="Opportunity attack provoked"]')
        expect(oa).to_be_visible(timeout=4000)
        expect(oa).to_contain_text("Opportunity Attack provoked")
        expect(oa.get_by_role("button", name="Continue anyway")).to_be_visible()
        stop = oa.get_by_role("button", name="Stop")
        expect(stop).to_be_visible()

        stop.click()
        expect(oa).to_have_count(0, timeout=2000)
        gm_page.wait_for_timeout(400)
        after = _token_for_char(gm_page, pip["id"])
        assert after and abs(after["x"] - 280) < 1 and abs(after["y"] - 280) < 1, (
            f"Stop must snap Pip back to (280,280); got ({after['x']},{after['y']})"
        )
        assert not errs, f"JS errors: {errs}"
    finally:
        gm_page.evaluate("() => { if (window.__origFetch) window.fetch = window.__origFetch; }")
        _clear_battle_server(gm_page)
