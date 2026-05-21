"""test_massive_damage_instakill — Phase 4 (Level 3), commit P.

Validates the 5e RAW **massive damage instakill** rule: when a
creature at HP X takes damage D such that the REMAINING damage past
0 (i.e. ``D - X``) is ≥ max_hp, the creature is killed outright —
skipping the dying state. See tabletop_routes.py:10821.

Scenario:
  1. Pip alive at hp_cur=35, hp_max=35.
  2. PATCH ``/sheet-fields`` with ``hp.current=0`` + ``hp_change_
     reason="damage"`` + ``damage_amount=70``. Remaining past 0 is
     ``70 - 35 = 35``, which equals max_hp → instakill.
  3. Server broadcasts ``character_death_save`` with
     ``status="dead"``, ``successes=0``, ``failures=0``.
  4. Tracker DOM reflects the dead status (data-status="dead",
     badge text "DEAD", failure pips off — instakill resets
     counters per the route logic at line 10846).
  5. Teardown: restore Pip to alive.

Companion to ``test_dies_after_3_failures``: that test goes dying →
3 failure ticks → dead. This test skips the dying state entirely
because the damage was massive. Both terminate in the same "dead"
state but exercise different state-machine branches.
"""
from __future__ import annotations

from playwright.sync_api import BrowserContext, expect

from ...conftest import tabletop_url
from ...helpers.battle import (
    apply_damage,
    death_save_override,
    make_combatant,
    seed_battle,
    seed_battle_into_page,
)
from ...helpers.ws import WSCollector
from ...pages.tabletop import TabletopPage


PIP_CID = "es_instakill_pip"


def test_pip_alive_to_dead_via_massive_damage(
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
        # Pre-condition: alive.
        expect(tracker).to_have_attribute("data-status", "alive", timeout=3000)

        # ── Apply massive damage ──────────────────────────────────
        # Pip max HP = 35. Send hp.current=0 + damage_amount=70.
        # Remaining past 0 = 70 - 35 = 35 ≥ max_hp → instakill.
        resp = apply_damage(
            pip["id"], damage_amount=70, new_hp_current=0,
            damage_type="bludgeoning",
        )
        assert resp.status_code == 200, resp.text

        # ── Server broadcasts character_death_save with dead ──────
        ws.wait_for(
            "character_death_save", timeout_ms=5000,
            predicate=lambda f: (
                f["data"].get("character_id") == pip["id"]
                and f["data"].get("status") == "dead"
            ),
        )

        # ── Tracker DOM reflects dead ─────────────────────────────
        expect(tracker).to_have_attribute("data-status", "dead", timeout=3000)
        # Instakill resets counters (route logic line 10846).
        expect(tracker).to_have_attribute("data-successes", "0", timeout=3000)
        expect(tracker).to_have_attribute("data-failures", "0", timeout=3000)

        badge = tracker.locator(".death-saves-status").first
        expect(badge).to_have_text("DEAD", timeout=3000)
    finally:
        death_save_override(pip["id"], status="alive", successes=0, failures=0)
