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
            window._targetingState = { tokenIds: [] };
            const before = { any: V.anySelected(), onTop: V.drawsOnTop({ id: 1, size: 1 }) };
            // Selecting a token suppresses the "everything on top" redraw.
            window._targetingState = { tokenIds: [1] };
            const after = { any: V.anySelected(), onTop: V.drawsOnTop({ id: 1, size: 1 }) };
            window._targetingState = { tokenIds: [] };
            return { before, after, isGm: !!(window.ME && window.ME.isGm) };
        }"""
    )
    assert r["isGm"], r
    # No selection → the GM draws every visible token on top of all effects.
    assert r["before"]["any"] is False and r["before"]["onTop"] is True, r
    # A token selected → stop forcing tokens on top (narrow to its vision).
    assert r["after"]["any"] is True and r["after"]["onTop"] is False, r


def test_player_only_controlled_tokens_draw_on_top(alice_page: Page) -> None:
    alice_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
    alice_page.wait_for_function("() => window.__tokenVisForTest && window.ME", timeout=8000)
    alice_page.wait_for_timeout(300)

    r = alice_page.evaluate(
        """() => {
            const V = window.__tokenVisForTest;
            window._targetingState = { tokenIds: [] };
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
    # Only the controlled token is forced on top; the other stays under the veil.
    assert r["onTopMine"] is True and r["onTopTheirs"] is False, r
