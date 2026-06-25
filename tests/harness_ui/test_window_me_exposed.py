"""Regression: `window.ME` must be exposed on the play surfaces.

The user identity is declared as a top-level ``const ME = {...}`` in the
page templates. A top-level ``const`` is *lexical* — it does NOT attach a
property to ``window``. But ``reaction_prompt.js`` (``window.ME.id`` /
``window.ME.reactionPromptMode``) and ``roll_toast.js`` (``window.ME.id`` /
``window.ME.isGm``) both read ``window.ME``. When it's undefined,
``reaction_prompt.js`` computes ``meId = null`` and suppresses **every**
reaction popup — the v2.640.1 "GM moves a PC → no OA prompt" bug (the OA
``reaction_prompt`` was broadcast correctly server-side, but the GM's
browser never rendered it).

The templates now do ``window.ME = ME;`` after the declaration. These tests
lock that in. Pure browser-JS defect — the HTTP/WS harness can't see it, so
it lives in the Playwright UI harness.
"""
from __future__ import annotations

from playwright.sync_api import Page

from tests.harness_ui.conftest import sheet_url, tabletop_url


def test_window_me_exposed_on_tabletop_for_gm(gm_page: Page):
    gm_page.goto(tabletop_url())
    gm_page.wait_for_selector("body")
    me = gm_page.evaluate("() => window.ME || null")
    assert me is not None, "window.ME undefined — reaction popups are suppressed"
    assert me.get("id"), f"window.ME.id missing: {me!r}"
    assert me.get("isGm") is True, f"GM session but isGm not true: {me!r}"
    assert me.get("reactionPromptMode"), "reactionPromptMode missing"


def test_window_me_exposed_on_tabletop_for_player(alice_page: Page):
    alice_page.goto(tabletop_url())
    alice_page.wait_for_selector("body")
    me = alice_page.evaluate("() => window.ME || null")
    assert me is not None, "window.ME undefined for player — reaction popups suppressed"
    assert me.get("id"), f"window.ME.id missing: {me!r}"


def test_window_me_exposed_on_character_sheet(alice_page: Page, roster: dict):
    char_id = roster["Pip Quickfingers"]["id"]
    alice_page.goto(sheet_url(char_id))
    alice_page.wait_for_selector("body")
    # roll_toast.js (loaded by sheet_dnd5e.html) reads window.ME.id for
    # roll-visibility / GM detection on the standalone sheet too.
    assert alice_page.evaluate("() => !!(window.ME && window.ME.id)"), (
        "window.ME.id undefined on the character sheet"
    )
