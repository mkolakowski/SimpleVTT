"""v2.100.5 — UI regression coverage for the pre-move movement modals
shipped in v2.100.0–.2. These are pure client-side gating flows on the
canvas drag handler (`_commitTokenMove` in tabletop.js) that the
HTTP+WS harness can't reach — it has no DOM, no canvas, no modal.

Covered:
  * v2.100.0 — GM over-range modal: dragging a NON-active token past
    its base walking speed during an active battle (with no OA in
    play) pops the "Moving past speed" advisory (Cancel / Move
    anyway). Cancel snaps back.
  * v2.100.2 — the pre-move Dash modal (over-cap move that provokes an
    OA) offers exactly "Cancel move" + "Take Dash" — the old "Skip
    Dash" button is gone, and Cancel makes no move + shows no OA.

Staging notes:
  - Battle state has TWO homes that both matter here:
      * the SERVER hub state (``PUT /battle``) — the OA preview
        (``_check_opportunity_attack_triggers``) and the over-speed
        gate read this, so it decides whether a drag provokes an OA.
      * the CLIENT ``battle`` closure — ``_getActiveCombatant`` reads
        this for ``_activeForDash`` / ``_anyActive``. The GM page
        IGNORES real ``battle_update`` broadcasts (GM is source of
        truth), so we seed the client side by dispatching a synthetic
        ``vtt:ws-message`` with ``force_gm_sync: true``.
    Each test sets BOTH to the same combatants so server + client agree.
  - World→screen mapping uses the SAME math as the canvas's own
    ``clientToCanvas``: ``screen = rect.left + (world + stripH) *
    scale`` where ``scale = rect.width / offsetWidth`` (offsetWidth
    excludes the CSS transform) and ``stripH`` is the v2.88.0 gutter
    from ``canvas.dataset.stripH``. Omitting stripH makes the
    mousedown miss the token entirely.
"""
from __future__ import annotations

from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def _wait_ready(page: Page) -> None:
    expect(page.locator("#vtt-canvas")).to_be_visible(timeout=8000)
    page.wait_for_function(
        "() => typeof window.vttGetCharacters === 'function'", timeout=5000,
    )


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
        {"cid": CAMPAIGN_ID, "charId": char_id, "x": x, "y": y},
    )


def _move_token(page: Page, token_id: int, x: float, y: float) -> None:
    page.evaluate(
        """async ({cid, tid, x, y}) => {
            await fetch('/api/campaign/'+cid+'/token/'+tid+'/move', {
                method: 'POST', credentials: 'include',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({x, y, override: true}),
            });
        }""",
        {"cid": CAMPAIGN_ID, "tid": token_id, "x": x, "y": y},
    )


def _token_for_char(page: Page, char_id: int) -> dict | None:
    tokens = page.evaluate(
        """async (cid) => {
            const r = await fetch('/api/campaign/'+cid+'/tokens', {credentials:'include'});
            return (await r.json()).tokens || [];
        }""",
        CAMPAIGN_ID,
    )
    return next((t for t in tokens if t.get("character_id") == char_id), None)


def _seed_battle(page: Page, combatants: list[dict], turn_index: int = 0) -> None:
    """Set BOTH battle homes to the same state: the server hub (PUT
    /battle — read by the OA preview + over-speed gate) and the client
    closure (synthetic force_gm_sync event — read by
    _getActiveCombatant). They must agree or the server says "OA!"
    while the client thinks otherwise (or vice versa)."""
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
        }""",
        {"cid": CAMPAIGN_ID, "payload": payload},
    )


def _clear_battle_server(page: Page) -> None:
    page.evaluate(
        """async (cid) => {
            await fetch('/api/campaign/'+cid+'/battle', {
                method: 'PUT', credentials: 'include',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({combatants: [], round: 0, turn_index: 0, active: false}),
            });
        }""",
        CAMPAIGN_ID,
    )


def _canvas_geo(page: Page) -> dict:
    return page.evaluate(
        """() => {
            const c = document.getElementById('vtt-canvas');
            const r = c.getBoundingClientRect();
            return {left: r.x, top: r.y, rw: r.width, offW: c.offsetWidth,
                    strip: +(c.dataset.stripH || 0), grid: +c.dataset.gridSize || 70};
        }"""
    )


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


def test_gm_over_range_modal_appears_and_cancels(gm_page: Page, roster: dict) -> None:
    """v2.100.0 — GM drags a non-active token (Pip) ~30 ft (past his
    25 ft speed) during an active battle, with the only combatant
    (Krieger) parked far away so no OA is in play → the "Moving past
    speed" advisory appears, and Cancel snaps Pip back.
    """
    pip = roster["Pip Quickfingers"]
    krieger = roster["Krieger Stonefist"]
    errs: list[str] = []
    gm_page.on("pageerror", lambda e: errs.append(str(e)))

    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
    _wait_ready(gm_page)
    _place_token(gm_page, pip["id"], 280.0, 280.0)
    # Park Krieger's token far from Pip's drag path so the seeded
    # watcher can't provoke an OA (which would route to the OA branch).
    kr_tok0 = _token_for_char(gm_page, krieger["id"])
    if kr_tok0:
        _move_token(gm_page, kr_tok0["id"], 1330.0, 910.0)
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
    _wait_ready(gm_page)

    kr_tok = _token_for_char(gm_page, krieger["id"])
    try:
        # Battle (server + client) whose ONLY combatant is Krieger,
        # parked far away → preview reports no OA. Pip isn't in init, so
        # the dragged token is non-active → over-range branch (not the
        # active-combatant overrun branch) is what fires.
        _seed_battle(gm_page, [
            {"char_id": krieger["id"], "name": krieger["name"], "init": 18,
             "speed_walk": 30, "id": "kr-1",
             "source_token_id": (kr_tok or {}).get("id", -999),
             "economy": {"action": False, "bonus": False, "reaction": False,
                         "movement": 0, "dash_bonus_ft": 0}},
        ])
        assert gm_page.evaluate(
            "() => !!(window._getActiveCombatant && window._getActiveCombatant())"
        ), "battle seed failed — no active combatant"

        geo = _canvas_geo(gm_page)
        half = geo["grid"] / 2
        start = _world_to_screen(geo, 280 + half, 280 + half)
        end = _world_to_screen(geo, 280 + half + geo["grid"] * 6, 280 + half)  # 30 ft east
        _drag(gm_page, start, end)

        modal = gm_page.locator('div[role="dialog"][aria-label="Token moved past its speed"]')
        expect(modal).to_be_visible(timeout=4000)
        expect(modal).to_contain_text("Moving past speed")
        expect(modal.get_by_role("button", name="Move anyway")).to_be_visible()
        cancel = modal.get_by_role("button", name="Cancel")
        expect(cancel).to_be_visible()

        cancel.click()
        expect(modal).to_have_count(0, timeout=2000)
        gm_page.wait_for_timeout(400)
        after = _token_for_char(gm_page, pip["id"])
        assert after and abs(after["x"] - 280) < 1 and abs(after["y"] - 280) < 1, (
            f"Cancel should snap Pip back to (280,280); got ({after['x']},{after['y']})"
        )
        assert not errs, f"JS errors: {errs}"
    finally:
        _clear_battle_server(gm_page)


def test_dash_modal_has_no_skip_button(gm_page: Page, roster: dict) -> None:
    """v2.100.2 — an over-cap move that provokes an OA pops the Dash
    modal with exactly "Cancel move" + "Take Dash" — no "Skip Dash".
    Clicking Cancel makes no move and never shows the OA modal.
    """
    pip = roster["Pip Quickfingers"]
    krieger = roster["Krieger Stonefist"]
    errs: list[str] = []
    gm_page.on("pageerror", lambda e: errs.append(str(e)))

    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
    _wait_ready(gm_page)
    # Pip (mover) at (280,280); Krieger (watcher) one cell NORTH (5 ft).
    # Dragging Pip east immediately grows the gap → exits reach (OA).
    _place_token(gm_page, pip["id"], 280.0, 280.0)
    _place_token(gm_page, krieger["id"], 280.0, 210.0)
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
    _wait_ready(gm_page)

    pip_tok = _token_for_char(gm_page, pip["id"])
    kr_tok = _token_for_char(gm_page, krieger["id"])
    assert pip_tok and kr_tok

    try:
        _seed_battle(gm_page, [
            {"char_id": pip["id"], "name": pip["name"], "init": 20,
             "speed_walk": 25, "id": "pip-1", "team": "hero",
             "source_token_id": pip_tok["id"],
             "economy": {"action": False, "bonus": False, "reaction": False,
                         "movement": 0, "dash_bonus_ft": 0}},
            {"char_id": krieger["id"], "name": krieger["name"], "init": 10,
             "speed_walk": 30, "id": "kr-1", "team": "villain",
             "source_token_id": kr_tok["id"],
             "economy": {"action": False, "bonus": False, "reaction": False,
                         "movement": 0, "dash_bonus_ft": 0}},
        ], turn_index=0)

        geo = _canvas_geo(gm_page)
        half = geo["grid"] / 2
        start = _world_to_screen(geo, 280 + half, 280 + half)
        end = _world_to_screen(geo, 280 + half + geo["grid"] * 6, 280 + half)  # 30 ft east
        _drag(gm_page, start, end)

        dash = gm_page.locator('div[role="dialog"][aria-label="Dash before opportunity attack"]')
        expect(dash).to_be_visible(timeout=4000)
        expect(dash.get_by_role("button", name="Take Dash")).to_be_visible()
        expect(dash.get_by_role("button", name="Cancel move")).to_be_visible()
        assert dash.get_by_text("Skip Dash").count() == 0, (
            "v2.100.2 removed the Skip Dash button — it must not render"
        )

        dash.get_by_role("button", name="Cancel move").click()
        expect(dash).to_have_count(0, timeout=2000)
        oa = gm_page.locator('div[role="dialog"][aria-label="Opportunity attack provoked"]')
        expect(oa).to_have_count(0)
        gm_page.wait_for_timeout(400)
        after = _token_for_char(gm_page, pip["id"])
        assert after and abs(after["x"] - 280) < 1 and abs(after["y"] - 280) < 1, (
            f"Cancel must not move Pip; got ({after['x']},{after['y']})"
        )
        assert not errs, f"JS errors: {errs}"
    finally:
        _clear_battle_server(gm_page)
