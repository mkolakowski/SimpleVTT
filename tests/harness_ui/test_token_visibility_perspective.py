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


def test_player_my_tokens_on_top_toggle_gates_turn_behavior(alice_page: Page) -> None:
    """v2.944.0 / v2.946.0 — the "⬆ My tokens on top" toggle (default ON) keeps a
    player's controlled tokens on top at all times. Unchecked, the v2.944.0 rule
    applies: during a live battle they ride on top only on their own turn."""
    alice_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
    alice_page.wait_for_function("() => window.__tokenVisForTest && window.ME", timeout=8000)
    alice_page.wait_for_timeout(300)

    r = alice_page.evaluate(
        """() => {
            const V = window.__tokenVisForTest;
            window._targetingState = { tokenIds: new Set() };
            const myId = window.ME.id;
            const mine = { id: 10, size: 1, controller_user_id: myId };
            // Live initiative; the OTHER combatant is active → my token is off-turn.
            window.battle = { active: true, turn_index: 1,
                combatants: [{ id: 1, source_token_id: 10 }, { id: 2, source_token_id: 77 }] };
            // Toggle ON (default) → on top even off-turn.
            localStorage.setItem('tt-mytokens-ontop', '1');
            const onTopWhenAlwaysOn = V.drawsOnTop(mine);
            // Toggle OFF → turn-gated: off-turn drops under the veil…
            localStorage.setItem('tt-mytokens-ontop', '0');
            const offTurnGated = V.drawsOnTop(mine);
            // …and on its own turn it rides on top again.
            window.battle.turn_index = 0;
            const onTurnGated = V.drawsOnTop(mine);
            localStorage.removeItem('tt-mytokens-ontop');
            window.battle = { active: false, combatants: [], turn_index: 0 };
            return { onTopWhenAlwaysOn, offTurnGated, onTurnGated };
        }"""
    )
    assert r["onTopWhenAlwaysOn"] is True, r   # toggle ON → always on top
    assert r["offTurnGated"] is False, r       # toggle OFF, off-turn → under veil
    assert r["onTurnGated"] is True, r         # toggle OFF, on-turn → on top


def test_my_tokens_on_top_toggle_renders_for_player_and_persists(alice_page: Page) -> None:
    """v2.946.0 — the "⬆ My tokens on top" checkbox shows for a player, defaults
    checked, and persists to localStorage when unchecked."""
    alice_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
    alice_page.wait_for_selector("#mytokens-ontop-cb", timeout=8000)
    cb = alice_page.locator("#mytokens-ontop-cb")
    assert cb.is_checked(), "toggle should default ON"
    cb.uncheck()
    stored = alice_page.evaluate("() => localStorage.getItem('tt-mytokens-ontop')")
    assert stored == "0", stored
    alice_page.evaluate("() => localStorage.removeItem('tt-mytokens-ontop')")


def test_my_tokens_on_top_toggle_hidden_for_gm(gm_page: Page) -> None:
    """v2.946.0 — the player-only toggle is not rendered for the GM (whose idle
    view already puts every token on top)."""
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
    gm_page.wait_for_selector("#token-veil-canvas", timeout=8000)
    assert gm_page.locator("#mytokens-ontop-cb").count() == 0
