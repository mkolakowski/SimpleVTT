"""Phase 4 — the canonical v2.7.3 regression target.

When a player clicks 🗡 Strike on a weapon attack on the standalone
character sheet, the roll-toast (``.roll-toast`` element rendered by
``app/static/roll_toast.js``) must appear in the DOM with text
matching the attack name. v2.7.3 was the case where the broadcast
fired correctly but the toast listener filtered for ``type === "roll"``
only, missing the ``weapon_attack`` type — the toast never rendered
even though the roll log card did. This test would have failed at
HEAD that day.

Coverage:
  - Pip's Shortsword strike → toast labelled "Shortsword — attack"
    (or similar) appears within 3 seconds
  - Tavik's Warhammer strike (the original v2.7.3 reproducer) → same
"""
from playwright.sync_api import Page, expect

from .conftest import sheet_url


def _click_first_atk_strike(page: Page) -> None:
    """Click the first ``.atk-strike`` and dismiss any modal pickers
    that pop along the way.

    v2.49.236: pre-v2.29.0 this was a simple click. The v2.16.0 uplift
    modal (Rogue Sneak Attack, Paladin Divine Smite) and v2.29.0 target
    picker (any PC, any attack, when no target is pre-selected via the
    tabletop's localStorage targeting mirror) now intercept the click
    on the standalone sheet. The test's intent is "Strike fires a
    toast", so we click through both modals with no-uplift + no-target
    selections and let the attack land.

    Order matters: uplift modal fires FIRST (immediately after the
    .atk-strike click) and the target picker is awaited inside the
    handler's ``try {}`` block, so it only renders after the uplift
    modal has been resolved (or skipped, if no uplifts apply).
    """
    strike = page.locator(".atk-strike").first
    expect(strike).to_be_visible(timeout=3000)
    strike.click()
    # Uplift modal (Pip's Sneak Attack, etc.) — click ⚔ Strike to
    # confirm without selecting any uplift. Skip when absent.
    uplift_confirm = page.locator("#uplift-modal #up-confirm")
    if uplift_confirm.count():
        try:
            uplift_confirm.click(timeout=1500)
        except Exception:
            pass  # already gone or never appeared
    # Target picker — click "Skip (no target)" so the attack still
    # fires against no target. Some attack handlers proceed without
    # one; either way the toast renders.
    skip = page.locator(".target-picker-skip")
    if skip.count():
        try:
            skip.click(timeout=1500)
        except Exception:
            pass


def test_pip_shortsword_strike_fires_roll_toast(gm_page: Page, roster: dict):
    pip = roster["Pip Quickfingers"]
    gm_page.goto(sheet_url(pip["id"]))
    expect(gm_page.locator("#attacks-fieldset")).to_be_visible(timeout=3000)
    _click_first_atk_strike(gm_page)
    # Roll toast appears in the body (anchored top-right typically).
    # The .roll-toast class is set by app/static/roll_toast.js's
    # showRollToast helper. Two toasts fire per attack (attack +
    # damage); we just need ONE to be visible.
    toast = gm_page.locator(".roll-toast").first
    expect(toast).to_be_visible(timeout=3000)
    # The label format is "🎲 Pip Quickfingers — 🎯 Shortsword — attack"
    # (matches the .atk-strike click handler in sheet_dnd5e.html). We
    # check just for the attack name to keep the assertion resilient
    # against label wording tweaks.
    expect(toast.locator(".rt-label")).to_contain_text("Shortsword", timeout=3000)


def test_tavik_warhammer_strike_fires_roll_toast(gm_page: Page, roster: dict):
    """The exact v2.7.3 regression scenario: Tavik's Warhammer.
    Pre-fix this test would have failed because no .roll-toast
    appeared even though the /attack endpoint succeeded."""
    tavik = roster["Brother Tavik Stonebrow"]
    gm_page.goto(sheet_url(tavik["id"]))
    expect(gm_page.locator("#attacks-fieldset")).to_be_visible(timeout=3000)
    _click_first_atk_strike(gm_page)
    toast = gm_page.locator(".roll-toast").first
    expect(toast).to_be_visible(timeout=3000)
    expect(toast.locator(".rt-label")).to_contain_text("Warhammer", timeout=3000)
