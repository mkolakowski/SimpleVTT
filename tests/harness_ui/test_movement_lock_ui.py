"""v2.103.0 — movement-lock UI (Phase 2).

The GM-only 🔒/🔓 toggle in the canvas-tools cluster flips the live
lock via POST /movement_lock; the movement_lock_update WS broadcast
keeps every client's window._MOVEMENT_LOCKED flag (and the GM button
chrome) in sync. These are pure client-side concerns the HTTP+WS
harness can't reach (no DOM / no button); the server gate itself is
covered by tests/harness/test_movement_lock.py.

Covered:
  * GM toggle button exists, starts unlocked, and round-trips the
    lock state (button label + aria-pressed + window._MOVEMENT_LOCKED)
    through POST /movement_lock.
  * The lock state propagates to a player's already-open tab via the
    movement_lock_update WS broadcast, and players never get the
    toggle button in their DOM.
  * No uncaught console errors on load (catches JS syntax regressions
    in the Phase 2 tabletop.js edits).

Always unlocks in a finally so a failure doesn't strand the demo
campaign locked for the rest of the suite.
"""
from __future__ import annotations

from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def _wait_ready(page: Page) -> None:
    expect(page.locator("#vtt-canvas")).to_be_visible(timeout=8000)
    page.wait_for_function(
        "() => typeof window.vttGetCharacters === 'function'", timeout=5000,
    )


def _set_lock(page: Page, locked: bool) -> None:
    # Absolute URL so this works even before the first goto() (the page
    # is on about:blank then, so a relative fetch URL won't parse).
    page.evaluate(
        """async ({base, cid, locked}) => {
            await fetch(base+'/api/campaign/'+cid+'/movement_lock', {
                method: 'POST', credentials: 'include',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({locked}),
            });
        }""",
        {"base": BASE_URL, "cid": CAMPAIGN_ID, "locked": locked},
    )


def test_gm_movement_lock_toggle(gm_page: Page) -> None:
    errors: list[str] = []
    gm_page.on("console", lambda m: errors.append(m.text)
               if m.type == "error" else None)
    try:
        gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
        _wait_ready(gm_page)
        # Normalize to unlocked via the WS path (also exercises the
        # movement_lock_update handler on the GM page).
        _set_lock(gm_page, False)
        gm_page.wait_for_function(
            "() => window._MOVEMENT_LOCKED === false", timeout=4000,
        )

        btn = gm_page.locator("#movement-lock-btn")
        expect(btn).to_be_visible(timeout=5000)
        expect(btn).to_have_attribute("aria-pressed", "false")

        # Click → locks. Button label + flag + aria-pressed all flip.
        btn.click()
        gm_page.wait_for_function(
            "() => window._MOVEMENT_LOCKED === true", timeout=4000,
        )
        expect(btn).to_have_attribute("aria-pressed", "true")
        assert "🔒" in btn.inner_text()

        # Click again → unlocks.
        btn.click()
        gm_page.wait_for_function(
            "() => window._MOVEMENT_LOCKED === false", timeout=4000,
        )
        expect(btn).to_have_attribute("aria-pressed", "false")

        assert not errors, f"console errors on the GM tabletop: {errors}"
    finally:
        _set_lock(gm_page, False)


def test_lock_propagates_to_player_and_player_has_no_toggle(
    gm_page: Page, alice_page: Page,
) -> None:
    try:
        # GM page first so we have a same-origin page to drive the API.
        gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
        _wait_ready(gm_page)
        _set_lock(gm_page, False)

        alice_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
        _wait_ready(alice_page)

        # Player has the live flag but NOT the GM-only toggle button.
        alice_page.wait_for_function(
            "() => window._MOVEMENT_LOCKED === false", timeout=4000,
        )
        expect(alice_page.locator("#movement-lock-btn")).to_have_count(0)

        # GM locks via the API; the WS broadcast flips alice's flag.
        _set_lock(gm_page, True)
        alice_page.wait_for_function(
            "() => window._MOVEMENT_LOCKED === true", timeout=5000,
        )
    finally:
        _set_lock(gm_page, False)
