"""test_stabilize_after_3_successes — Phase 4 (Level 3), commit N.

First Level 3 edge-case test. Validates the **death-save state
machine + WS broadcast → DOM update** flow:

  1. Pre-condition: Pip is alive. The death-saves tracker partial
     (`_death_saves_tracker.html`, included by `_mini_sheet_card.html`)
     renders inside Pip's init-card with `data-status="alive"`.
  2. Override Pip to ``dying`` via ``POST /death-save/override``. The
     server broadcasts `character_death_save` with the new status;
     the JS handler `_onCharacterDeathSave` mutates the tracker
     `data-status` attribute in place.
  3. Override to ``stable`` with successes=3, failures=0. Another
     broadcast; the tracker updates again.
  4. Teardown: reset to alive so subsequent tests don't inherit a
     dying Pip.

This is the simplest possible Level 3 test — uses the override
endpoint instead of rolling the d20, so the outcome is
deterministic without dice seeding. Later commits will exercise
the rollable death-save endpoint with seeded dice for the
"3 failures → 💀 skull" path.
"""
from __future__ import annotations

from playwright.sync_api import BrowserContext, expect

from ...conftest import tabletop_url
from ...helpers.battle import (
    death_save_override,
    make_combatant,
    seed_battle,
    seed_battle_into_page,
)
from ...helpers.ws import WSCollector
from ...pages.tabletop import TabletopPage


PIP_CID = "es_ds_pip"


def test_pip_dying_to_stable_via_override(
    gm_context: BrowserContext,
    roster: dict,
):
    pip = roster["Pip Quickfingers"]
    # Defensive teardown safety: reset Pip to alive BEFORE the test
    # runs so prior aborted runs leaving her dying don't poison the
    # pre-condition check.
    death_save_override(pip["id"], status="alive", successes=0, failures=0)

    combatants = [
        make_combatant(
            PIP_CID, char_id=pip["id"], name="Pip Quickfingers",
            hp_cur=35, hp_max=35, initiative=15,
        ),
    ]
    seed_battle(combatants)
    seed_battle_into_page(gm_context, combatants)

    gm_page = gm_context.new_page()
    ws = WSCollector(gm_page)
    ws.start()
    gm_page.goto(tabletop_url())
    gm_page.evaluate("window._openDrawerPanel('players-drawer')")

    tabletop = TabletopPage(gm_page)
    expect(tabletop.combatant_row("Pip Quickfingers")).to_be_visible(timeout=5000)

    # The tracker lives inside the init-card-sheet div which is
    # display:none by default — but its data-status attribute is
    # readable from the DOM regardless of visibility. Locate by
    # data-character-id so we get exactly Pip's tracker (multiple
    # PCs may have trackers on the page).
    tracker = gm_page.locator(
        f'.death-saves-tracker[data-character-id="{pip["id"]}"]'
    ).first

    try:
        # ── Pre-condition: tracker reads "alive" ──────────────────
        expect(tracker).to_have_attribute("data-status", "alive", timeout=3000)

        # ── Step 1: override to dying ─────────────────────────────
        resp = death_save_override(pip["id"], status="dying")
        assert resp.status_code == 200, resp.text

        ws.wait_for(
            "character_death_save", timeout_ms=5000,
            predicate=lambda f: (
                f["data"].get("character_id") == pip["id"]
                and f["data"].get("status") == "dying"
            ),
        )
        expect(tracker).to_have_attribute("data-status", "dying", timeout=3000)

        # ── Step 2: override to stable with 3 successes ───────────
        resp2 = death_save_override(
            pip["id"], status="stable", successes=3, failures=0,
        )
        assert resp2.status_code == 200, resp2.text

        ws.wait_for(
            "character_death_save", timeout_ms=5000,
            predicate=lambda f: (
                f["data"].get("character_id") == pip["id"]
                and f["data"].get("status") == "stable"
            ),
        )
        expect(tracker).to_have_attribute("data-status", "stable", timeout=3000)
        expect(tracker).to_have_attribute("data-successes", "3", timeout=3000)
        expect(tracker).to_have_attribute("data-failures", "0", timeout=3000)

        # The status badge text also flips to "STABLE" (uppercase).
        badge = tracker.locator(".death-saves-status").first
        expect(badge).to_have_text("STABLE", timeout=3000)
    finally:
        # ── Teardown: restore Pip to alive ────────────────────────
        # death-save state persists in the character sheet row, so
        # without this every subsequent test that touches Pip would
        # see a stable Pip — confusing failure mode.
        death_save_override(pip["id"], status="alive", successes=0, failures=0)
