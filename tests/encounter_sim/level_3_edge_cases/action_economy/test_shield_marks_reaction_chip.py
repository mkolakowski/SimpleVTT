"""test_shield_marks_reaction_chip — Phase 4 (Level 3), commit Y.

Validates the **reaction-slot chip** flips when a reaction spell
fires. Shield (Wizard L1, casting_time="1 reaction") is the
canonical reaction spell — Thalindra casts it on herself to gain
+5 AC until her next turn. The server routes through the same
``_casting_time_to_economy`` mapping as action / bonus spells: a
"1 reaction" casting_time consumes the reaction slot.

Completes the action-economy chip-slot trifecta alongside:
  - commit R: Action Surge refunds the **action** chip.
  - commit S: Cunning Action consumes the **bonus** chip.
  - this commit: Shield consumes the **reaction** chip.

Scenario:
  1. Long-rest Thalindra so the L1 slot Shield consumes is full.
  2. Seed her into battle with default economy (all slots False).
  3. Pre-condition: reaction chip is NOT `.used`.
  4. POST `/cast_spell` for Shield (spell_index=4, slot_level=1,
     class_slug="wizard"). No target — self-buff.
  5. Wait for `economy_update` WS frame with `slot="reaction",
     used=True`.
  6. Post-condition: reaction chip is `.used`.
"""
from __future__ import annotations

import re

from playwright.sync_api import BrowserContext, expect

from ...conftest import tabletop_url
from ...helpers.battle import (
    cast_spell,
    make_combatant,
    seed_battle,
    seed_battle_into_page,
)
from ...helpers.reset import long_rest
from ...helpers.ws import WSCollector
from ...pages.tabletop import TabletopPage


THAL_CID = "es_shield_thal"
SHIELD_INDEX = 4  # Thalindra's wizard spell list (demo_seed.py:390)


def test_thalindra_shield_marks_reaction_chip(
    gm_context: BrowserContext,
    roster: dict,
):
    thal = roster["Thalindra Moonwhisper"]
    long_rest(thal["id"])

    combatants = [
        make_combatant(
            THAL_CID, char_id=thal["id"], name="Thalindra Moonwhisper",
            hp_cur=24, hp_max=24, initiative=15,
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
    expect(tabletop.combatant_row("Thalindra Moonwhisper")).to_be_visible(timeout=5000)

    reaction_chip = tabletop.combatant_row("Thalindra Moonwhisper").locator(
        '.econ-chip[data-slot="reaction"]'
    ).first

    # ── Pre-condition: reaction chip is available ─────────────────
    class_before = reaction_chip.get_attribute("class") or ""
    assert "used" not in class_before.split(), (
        f"reaction chip pre-condition: should not be .used; got class={class_before!r}"
    )

    # ── Cast Shield ───────────────────────────────────────────────
    resp = cast_spell(
        thal["id"], SHIELD_INDEX,
        slot_level=1, class_slug="wizard",
    )
    assert resp.status_code == 200, resp.text

    # ── Layer 2: economy_update with slot=reaction, used=True ─────
    eu = ws.wait_for(
        "economy_update", timeout_ms=5000,
        predicate=lambda f: (
            f["data"].get("character_id") == thal["id"]
            and f["data"].get("slot") == "reaction"
        ),
    )
    assert eu["data"]["used"] is True

    # ── Post-condition: reaction chip is now .used ────────────────
    reaction_chip_after = tabletop.combatant_row("Thalindra Moonwhisper").locator(
        '.econ-chip[data-slot="reaction"]'
    ).first
    expect(reaction_chip_after).to_have_class(re.compile(r"\bused\b"), timeout=3000)
