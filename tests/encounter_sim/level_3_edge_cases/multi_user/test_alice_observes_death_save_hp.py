"""test_alice_observes_death_save_hp — Phase 4 (Level 3), regression
test for v2.49.46.

Validates the v2.49.46 fix: ``character_death_save`` broadcasts that
carry an ``hp`` field also refresh the init tracker. Pre-fix, the
death-save handler updated the death-saves-tracker DOM + mini-sheet
card but skipped ``renderBattle``, leaving the init tracker's
``.mini-header-sub`` "HP X / Y" text stale.

Scenario:
  1. Pip is "dying" with hp_cur=0 (set via override).
  2. Open Alice's tabletop. Pre-condition: Pip's init-row shows
     "HP 0" (the dying state).
  3. GM calls ``death_save_override(status="alive", successes=0,
     failures=0)`` — this transitions Pip to alive AND bumps HP
     to 1 (the server's special-case at tabletop_routes.py:15171).
  4. Server broadcasts ``character_death_save`` with status=alive
     and hp.current=1.
  5. Pre-v2.49.46: Alice's death-saves tracker flipped to "ALIVE"
     correctly but her init-tracker mini-header-sub still said
     "HP 0" until something else triggered renderBattle.
     Post-v2.49.46: the handler also calls renderBattle so the
     init-tracker text reads "HP 1" immediately.

The bug surfaced during the v2.49.45 audit pass (filed in that
CHANGELOG as the next defensive renderBattle call to add). This
test pins it.
"""
from __future__ import annotations

import re

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


PIP_CID = "es_alice_ds_pip"


def test_alice_sees_pip_hp_jump_on_death_save_status_change(
    alice_context: BrowserContext,
    roster: dict,
):
    pip = roster["Pip Quickfingers"]
    # Set Pip's sheet HP to 0 via heal helper (the heal helper PATCHes
    # /sheet-fields with reason="set" — works for any positive value
    # including 0). Then override status to dying. The death-save
    # override doesn't itself touch HP, only status + counters.
    heal(pip["id"], hp_current=0)
    death_save_override(pip["id"], status="dying", successes=0, failures=0)

    combatants = [
        make_combatant(
            PIP_CID, char_id=pip["id"], name="Pip Quickfingers",
            hp_cur=0, hp_max=35, initiative=15,
        ),
    ]
    seed_battle(combatants)
    seed_battle_into_page(alice_context, combatants)

    alice_page = alice_context.new_page()
    ws = WSCollector(alice_page)
    ws.start()
    alice_page.goto(tabletop_url())
    alice_page.evaluate("window._openDrawerPanel('players-drawer')")

    pip_row = alice_page.locator(".init-entry").filter(
        has=alice_page.locator(".mini-header-name", has_text="Pip Quickfingers")
    ).first
    expect(pip_row).to_be_visible(timeout=5000)

    # Pre-condition: HP 0.
    hp_label = pip_row.locator(".mini-header-sub").first
    expect(hp_label).to_contain_text("0", timeout=3000)

    try:
        # ── GM overrides Pip to alive ─────────────────────────────
        # The endpoint bumps HP from 0 → 1 as part of the "alive at
        # 0 HP would immediately re-fall to dying" sanity check.
        resp = death_save_override(
            pip["id"], status="alive", successes=0, failures=0,
        )
        assert resp.status_code == 200, resp.text

        # ── Layer 2: character_death_save broadcast with hp.current=1
        frame = ws.wait_for(
            "character_death_save", timeout_ms=5000,
            predicate=lambda f: (
                f["data"].get("character_id") == pip["id"]
                and f["data"].get("status") == "alive"
            ),
        )
        assert frame["data"]["hp"]["current"] == 1, (
            f"override(alive) on a 0-HP PC should bump HP to 1; got "
            f"{frame['data']['hp']}"
        )

        # ── Layer 6: Alice's init-tracker shows HP 1 ──────────────
        # v2.49.46 fix: the death-save handler now refreshes the
        # init tracker so the mini-header-sub picks up the new HP.
        pip_row_after = alice_page.locator(".init-entry").filter(
            has=alice_page.locator(".mini-header-name", has_text="Pip Quickfingers")
        ).first
        hp_label_after = pip_row_after.locator(".mini-header-sub").first

        # Wait briefly for the re-render to settle. The handler call
        # is synchronous from the WS frame dispatch, but Playwright's
        # frame-lifecycle observation has a small lag.
        alice_page.wait_for_timeout(200)

        label_text = hp_label_after.inner_text()
        cur_match = re.search(r"HP\s*(\d+)\s*/\s*(\d+)", label_text)
        assert cur_match, f"could not parse HP from {label_text!r}"
        cur = int(cur_match.group(1))
        assert cur == 1, (
            f"init-tracker shows HP {cur} but should show 1 after "
            f"override(alive). v2.49.46 regression — the "
            f"character_death_save handler should refresh the "
            f"init-tracker mini-header via renderBattle when the "
            f"broadcast includes hp."
        )
    finally:
        # Restore Pip to fully alive at max for subsequent tests.
        death_save_override(pip["id"], status="alive", successes=0, failures=0)
