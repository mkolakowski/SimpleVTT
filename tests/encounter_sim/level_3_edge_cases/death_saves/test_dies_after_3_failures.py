"""test_dies_after_3_failures — Phase 4 (Level 3), commit N.

Companion to ``test_stabilize_after_3_successes``. Validates the
**dead** terminal state of the death-save machine: Pip goes dying →
3 failures → dead. Tracker `data-status` reads "dead" with
failures=3; the status badge text flips to "DEAD".

The plan's matching scenario also asserts on the v2.49.4 💀 skull
canvas overlay (which is what motivated this whole encounter-sim
suite — see plan intro). Canvas pixel-sampling needs a helper in
``pages/canvas.py`` that doesn't exist yet; the overlay test is
filed for the canvas-reader commit that lands next.

State transitions exercise the same broadcast path as the stabilize
test (``character_death_save``) but assert on the terminal "dead"
state instead of "stable". The two tests together cover the
3-success and 3-failure branches of the state machine.
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


PIP_CID = "es_ds_pip_dead"


def test_pip_dying_to_dead_via_override(
    gm_context: BrowserContext,
    roster: dict,
):
    pip = roster["Pip Quickfingers"]
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

    tracker = gm_page.locator(
        f'.death-saves-tracker[data-character-id="{pip["id"]}"]'
    ).first

    try:
        expect(tracker).to_have_attribute("data-status", "alive", timeout=3000)

        # Override to dying.
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

        # Override to dead with 3 failures.
        resp2 = death_save_override(
            pip["id"], status="dead", successes=0, failures=3,
        )
        assert resp2.status_code == 200, resp2.text
        ws.wait_for(
            "character_death_save", timeout_ms=5000,
            predicate=lambda f: (
                f["data"].get("character_id") == pip["id"]
                and f["data"].get("status") == "dead"
            ),
        )

        expect(tracker).to_have_attribute("data-status", "dead", timeout=3000)
        expect(tracker).to_have_attribute("data-failures", "3", timeout=3000)
        expect(tracker).to_have_attribute("data-successes", "0", timeout=3000)

        badge = tracker.locator(".death-saves-status").first
        expect(badge).to_have_text("DEAD", timeout=3000)
    finally:
        death_save_override(pip["id"], status="alive", successes=0, failures=0)
