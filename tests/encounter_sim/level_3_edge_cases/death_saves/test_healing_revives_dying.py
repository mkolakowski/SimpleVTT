"""test_healing_revives_dying — Phase 4 (Level 3), commit P.

Validates the **healing auto-revives** path of the death-save state
machine (see tabletop_routes.py:10810, "healing auto-revives"). A
PC who is dying / stable / dead becomes alive again the moment
their HP is set to a positive value. Used by Healing Word, Cure
Wounds, potions, and any other HP-restoring action.

Scenario:
  1. Pip is dying (HP=0, status="dying", successes=1, failures=1
     — set via override so we don't have to roll first).
  2. Healing arrives: PATCH ``/sheet-fields`` with ``hp.current=8``
     (no ``hp_change_reason`` field → reason="set"). Server flips
     status to "alive" and clears the death-save counters.
  3. ``character_death_save`` broadcast carries the new state.
  4. Tracker DOM transitions from dying → alive; successes &
     failures reset to 0.

This complements the "alive → dead" tests (3 successes / 3
failures / massive damage) with the reverse direction. Together
the four tests cover every entry / exit of the dying state.
"""
from __future__ import annotations

from playwright.sync_api import BrowserContext, expect

from ...conftest import tabletop_url
from ...helpers.battle import (
    death_save_override,
    heal,
    make_combatant,
    seed_battle,
    seed_battle_into_page,
)
from ...helpers.ws import WSCollector
from ...pages.tabletop import TabletopPage


PIP_CID = "es_heal_pip"


def test_healing_word_revives_dying_pip(
    gm_context: BrowserContext,
    roster: dict,
):
    pip = roster["Pip Quickfingers"]
    # Defensive entry reset.
    death_save_override(pip["id"], status="alive", successes=0, failures=0)
    # Now drop her to dying with some in-progress saves.
    death_save_override(pip["id"], status="dying", successes=1, failures=1)

    combatants = [
        make_combatant(
            PIP_CID, char_id=pip["id"], name="Pip Quickfingers",
            hp_cur=0, hp_max=35, initiative=15,
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

    tracker = gm_page.locator(
        f'.death-saves-tracker[data-character-id="{pip["id"]}"]'
    ).first

    try:
        # Pre-condition: dying with 1 success + 1 failure.
        expect(tracker).to_have_attribute("data-status", "dying", timeout=3000)
        expect(tracker).to_have_attribute("data-successes", "1", timeout=3000)
        expect(tracker).to_have_attribute("data-failures", "1", timeout=3000)

        # ── Heal ──────────────────────────────────────────────────
        # Healing Word at L1 heals 1d4+spellcasting; we send a flat
        # value to keep the test deterministic. The HP goes from 0
        # → 8, crossing the "alive again" threshold at HP > 0.
        resp = heal(pip["id"], hp_current=8)
        assert resp.status_code == 200, resp.text

        # ── Wait for the state-machine broadcast ──────────────────
        ws.wait_for(
            "character_death_save", timeout_ms=5000,
            predicate=lambda f: (
                f["data"].get("character_id") == pip["id"]
                and f["data"].get("status") == "alive"
            ),
        )

        # ── Tracker DOM transitions to alive + counters reset ─────
        expect(tracker).to_have_attribute("data-status", "alive", timeout=3000)
        expect(tracker).to_have_attribute("data-successes", "0", timeout=3000)
        expect(tracker).to_have_attribute("data-failures", "0", timeout=3000)

        badge = tracker.locator(".death-saves-status").first
        expect(badge).to_have_text("ALIVE", timeout=3000)
    finally:
        death_save_override(pip["id"], status="alive", successes=0, failures=0)
