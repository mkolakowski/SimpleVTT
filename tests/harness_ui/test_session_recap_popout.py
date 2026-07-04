"""v2.886.0 — the GM's End-Session recap popout.

Ending a session opens a glass dialog to name the session + jot GM-only
notes before it ends. Here we drive the popout directly (so we don't end
the live demo session) and assert its shape + that Cancel dismisses it.
"""
from __future__ import annotations

from playwright.sync_api import Page, expect

from .conftest import tabletop_url


def test_gm_end_session_recap_popout_renders_and_cancels(gm_page: Page) -> None:
    gm_page.goto(tabletop_url())
    gm_page.wait_for_function(
        "() => typeof window._showGmEndSessionRecap === 'function'", timeout=8000
    )
    # Open the recap popout directly (Cancel path — does NOT end the session).
    gm_page.evaluate("window._showGmEndSessionRecap()")

    dlg = gm_page.locator('[role="dialog"][aria-label="⏹ End session"]')
    expect(dlg).to_be_visible()
    # A nickname input + a GM-notes textarea + the End Session button.
    assert dlg.locator('input[type="text"]').count() == 1
    assert dlg.locator("textarea").count() == 1
    expect(dlg.locator("button", has_text="End Session")).to_be_visible()

    dlg.locator("button", has_text="Cancel").click()
    expect(dlg).to_have_count(0)
