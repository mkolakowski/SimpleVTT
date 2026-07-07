"""v2.882.0 — selection-aware token visibility + perspective ("The Watchful Eye").

Two behaviours, exposed through ``window.__tokenVisForTest``:

  * With NO token selected, tokens draw ON TOP of every effect for maximum
    visibility — GM sees every token above the lighting/fog veil; a player sees
    only the tokens they control on top.
  * Once a token IS selected (the targeting set is non-empty) the "on top"
    redraw is suppressed and the view narrows to that token's vision instead.
"""
from __future__ import annotations

from playwright.sync_api import Page

from .conftest import BASE_URL, CAMPAIGN_ID


def test_gm_all_tokens_on_top_until_one_is_selected(gm_page: Page) -> None:
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
    gm_page.wait_for_function("() => window.__tokenVisForTest", timeout=8000)
    gm_page.wait_for_timeout(300)

    r = gm_page.evaluate(
        """() => {
            const V = window.__tokenVisForTest;
            // v2.940.1 — the real targeting state stores `tokenIds` as a Set (not
            // an array); this test must mirror that shape so it catches a `.size`
            // vs `.length` regression in _anyTokenSelected.
            window._targetingState = { tokenIds: new Set() };
            const before = {
                any: V.anySelected(),
                onTopA: V.drawsOnTop({ id: 1, size: 1 }),
                onTopB: V.drawsOnTop({ id: 2, size: 1 }),
            };
            // v2.944.0 — targeting token 1: the TARGETED token rides on top (over
            // its POV veil), while a non-targeted token drops under the veil.
            window._targetingState = { tokenIds: new Set([1]) };
            const after = {
                any: V.anySelected(),
                onTopTargeted: V.drawsOnTop({ id: 1, size: 1 }),
                onTopOther: V.drawsOnTop({ id: 2, size: 1 }),
            };
            window._targetingState = { tokenIds: new Set() };
            return { before, after, isGm: !!(window.ME && window.ME.isGm) };
        }"""
    )
    assert r["isGm"], r
    # No selection → the GM draws every visible token on top of all effects.
    assert r["before"]["any"] is False, r
    assert r["before"]["onTopA"] is True and r["before"]["onTopB"] is True, r
    # A token targeted → only THAT token stays on top; others narrow under the veil.
    assert r["after"]["any"] is True, r
    assert r["after"]["onTopTargeted"] is True, r
    assert r["after"]["onTopOther"] is False, r


def test_player_only_controlled_tokens_draw_on_top(alice_page: Page) -> None:
    alice_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
    alice_page.wait_for_function("() => window.__tokenVisForTest && window.ME", timeout=8000)
    alice_page.wait_for_timeout(300)

    r = alice_page.evaluate(
        """() => {
            const V = window.__tokenVisForTest;
            window._targetingState = { tokenIds: new Set() };
            window.battle = { active: false, combatants: [], turn_index: 0 };  // exploration
            const myId = window.ME.id;
            const mine = { id: 10, size: 1, controller_user_id: myId };
            const theirs = { id: 11, size: 1, controller_user_id: myId + 9999, character_id: null };
            return {
                isGm: !!window.ME.isGm,
                controlsMine: V.controls(mine),
                controlsTheirs: V.controls(theirs),
                onTopMine: V.drawsOnTop(mine),
                onTopTheirs: V.drawsOnTop(theirs),
            };
        }"""
    )
    assert r["isGm"] is False, r
    # A player controls their own token but not someone else's.
    assert r["controlsMine"] is True and r["controlsTheirs"] is False, r
    # Out of combat (no live initiative), the controlled token rides on top; the
    # other stays under the veil.
    assert r["onTopMine"] is True and r["onTopTheirs"] is False, r


def test_player_controlled_token_on_top_only_on_its_turn(alice_page: Page) -> None:
    """v2.944.0 — during a live battle a player's controlled token rides on top
    only on its own turn; off-turn it drops under the veil."""
    alice_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
    alice_page.wait_for_function("() => window.__tokenVisForTest && window.ME", timeout=8000)
    alice_page.wait_for_timeout(300)

    r = alice_page.evaluate(
        """() => {
            const V = window.__tokenVisForTest;
            window._targetingState = { tokenIds: new Set() };
            const myId = window.ME.id;
            const mine = { id: 10, size: 1, controller_user_id: myId };
            // Live initiative; my token (id 10) is the active combatant.
            window.battle = { active: true, turn_index: 0,
                combatants: [{ id: 1, source_token_id: 10 }, { id: 2, source_token_id: 77 }] };
            const onTurn = V.drawsOnTop(mine);
            // Advance the turn to the other combatant → my token is off-turn.
            window.battle.turn_index = 1;
            const offTurn = V.drawsOnTop(mine);
            window.battle = { active: false, combatants: [], turn_index: 0 };
            return { onTurn, offTurn };
        }"""
    )
    # On its turn → on top; off its turn → under the veil.
    assert r["onTurn"] is True, r
    assert r["offTurn"] is False, r
