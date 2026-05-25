"""test_action_surge_refunds_chip — Phase 4 (Level 3), commit R.

Validates the Fighter's **Action Surge** feature's economy-chip
refund. RAW: Action Surge grants an additional action on the same
turn, exactly once between short rests. The server models this as
flipping the combatant's ``economy.action`` slot from used → not
used (refund), so the chip strip in the init tracker visually
re-enables the action.

Scenario:
  1. Long-rest Garrik so his Action Surge use is available
     (refreshes on short OR long rest).
  2. Seed battle state with Garrik's ``economy.action = True``
     (he already swung this turn).
  3. Open the GM tabletop + init drawer.
  4. Pre-condition: Garrik's action chip has the ``.used`` class.
  5. POST ``/use_action_surge`` for Garrik.
  6. Server broadcasts ``economy_update`` with ``slot=action,
     used=False``.
  7. Client's handler (tabletop.html:5556 — no IS_GM guard) updates
     the combatant + re-renders.
  8. Post-condition: Garrik's action chip no longer has ``.used``.

Complements commit J's strict-mode test (which validated the
OVER-budget gate) by exercising the OTHER end: a code path that
REFUNDS the action slot. Together they cover the two
non-trivial action-economy mutations the rules support.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import BrowserContext, expect

from ...conftest import tabletop_url
from ...helpers.battle import (
    make_combatant,
    post_use,
    seed_battle,
    seed_battle_into_page,
)
from ...helpers.reset import long_rest
from ...helpers.ws import WSCollector
from ...pages.tabletop import TabletopPage


GARRIK_CID = "es_surge_garrik"


@pytest.mark.skip(reason=(
    "v2.49.236: Garrik Ironside is no longer tokenized in the demo seed "
    "(slimmed to 6 PCs in v2.49.172). The init-tracker orphan-cleanup at "
    "tabletop.html:4807 drops his combatant when seeded directly. This "
    "test specifically requires a tokenized Fighter (for Action Surge); "
    "no other tokenized demo PC is a Fighter. Fix path: re-tokenize Garrik "
    "or change the demo's tokenized-six lineup to include a Fighter. "
    "Backbone Kristen (tests/harness/test_use_action_surge.py) still "
    "covers the chip-refund contract via direct PUT /battle; only this "
    "Playwright UI assertion is gated on the missing token."
))
def test_action_surge_refunds_action_chip(
    gm_context: BrowserContext,
    roster: dict,
):
    garrik = roster["Garrik Ironside"]
    # Action Surge refreshes on short rest; long rest is a superset
    # — guarantees the use is available regardless of prior tests.
    long_rest(garrik["id"])

    # Pre-mark Garrik's action slot used. The combatant builder's
    # default economy has all slots False; we mutate it directly
    # before seeding.
    garrik_combatant = make_combatant(
        GARRIK_CID, char_id=garrik["id"],
        name="Garrik Ironside", hp_cur=49, hp_max=49, initiative=18,
    )
    garrik_combatant["economy"]["action"] = True
    seed_battle([garrik_combatant])
    seed_battle_into_page(gm_context, [garrik_combatant])

    gm_page = gm_context.new_page()
    ws = WSCollector(gm_page)
    ws.start()
    gm_page.goto(tabletop_url())
    gm_page.evaluate("window._openDrawerPanel('players-drawer')")

    tabletop = TabletopPage(gm_page)
    expect(tabletop.combatant_row("Garrik Ironside")).to_be_visible(timeout=5000)

    # ── Pre-condition: action chip marked used ────────────────────
    action_chip = tabletop.combatant_row("Garrik Ironside").locator(
        '.econ-chip[data-slot="action"]'
    ).first
    expect(action_chip).to_have_class(__import__("re").compile(r"\bused\b"), timeout=3000)

    # ── Fire Action Surge ─────────────────────────────────────────
    resp = post_use("use_action_surge", garrik["id"])
    assert resp.status_code == 200, resp.text

    # ── Layer 2: economy_update WS frame with used=False ──────────
    eu = ws.wait_for(
        "economy_update", timeout_ms=5000,
        predicate=lambda f: (
            f["data"].get("character_id") == garrik["id"]
            and f["data"].get("slot") == "action"
        ),
    )
    assert eu["data"]["used"] is False, (
        f"Action Surge should refund the action slot (used=false); got {eu['data']}"
    )

    # ── Post-condition: action chip no longer .used ───────────────
    # The handler re-renders, so re-locate the chip from the row.
    action_chip_after = tabletop.combatant_row("Garrik Ironside").locator(
        '.econ-chip[data-slot="action"]'
    ).first
    # ``not.to_have_class`` is fragile (matches partial substrings);
    # use a Playwright class check via class_list inspection instead.
    class_attr = action_chip_after.get_attribute("class") or ""
    assert "used" not in class_attr.split(), (
        f"action chip still carries 'used' class after Action Surge: "
        f"class={class_attr!r}"
    )
