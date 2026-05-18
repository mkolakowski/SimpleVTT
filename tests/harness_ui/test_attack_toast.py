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
    """Wait for the first ``.atk-strike`` button to be visible + ready,
    then click it. ``.atk-strike`` is rendered inside the dynamic
    Attacks panel; the sheet's IIFE populates them after the page
    paints, so a fixed wait would race."""
    strike = page.locator(".atk-strike").first
    expect(strike).to_be_visible(timeout=3000)
    strike.click()


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
