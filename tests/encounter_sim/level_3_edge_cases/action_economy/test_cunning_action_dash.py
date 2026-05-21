"""test_cunning_action_dash — Phase 4 (Level 3), commit S.

Validates the Rogue's **Cunning Action** bonus-action feature. RAW:
"Starting at 2nd level, you can take a bonus action on each of your
turns in combat. This action can be used only to take the Dash,
Disengage, or Hide action." Server-side, this fires the generic
``/use_feature`` endpoint with ``feature_key="cunning-action" +
option_key="dash"/"disengage"/"hide"``, marks the bonus chip used,
broadcasts ``feature_used`` + ``economy_update``.

Scenario:
  1. Long-rest Pip + seed her into battle with bonus chip available
     (`economy.bonus = False`).
  2. Open GM tabletop + players panel.
  3. Pre-condition: bonus chip is NOT `.used`.
  4. POST `/use_feature` with cunning-action + dash.
  5. Wait for `economy_update` WS frame with `slot=bonus, used=True`.
  6. Post-condition: bonus chip is now `.used`.

Companion to commit R's Action Surge test:
  - Action Surge **refunds** the action chip (.used → not used).
  - Cunning Action **marks** the bonus chip (not used → .used).
The two together exercise both directions of the chip-toggling
state machine.

Only the Dash option is tested here; Disengage and Hide are
identical paths (different `option_key`, same code path). Filed
for parametrized expansion if it surfaces a meaningful regression
class.
"""
from __future__ import annotations

import re

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


PIP_CID = "es_cunning_pip"


def test_cunning_action_dash_marks_bonus_chip(
    gm_context: BrowserContext,
    roster: dict,
):
    pip = roster["Pip Quickfingers"]
    long_rest(pip["id"])

    # Default make_combatant has economy.bonus = False, which is the
    # pre-condition we want.
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

    bonus_chip = tabletop.combatant_row("Pip Quickfingers").locator(
        '.econ-chip[data-slot="bonus"]'
    ).first

    # ── Pre-condition: bonus chip is available ────────────────────
    class_before = bonus_chip.get_attribute("class") or ""
    assert "used" not in class_before.split(), (
        f"bonus chip pre-condition: should not be .used; got class={class_before!r}"
    )

    # ── Fire Cunning Action: Dash ─────────────────────────────────
    resp = post_use(
        "use_feature", pip["id"],
        extra={
            "feature_key": "cunning-action",
            "option_key": "dash",
            "label": "Cunning Action",
            "desc": "Move up to your speed again this turn.",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["slot"] == "bonus"
    assert "Cunning Action" in body["feature_label"]
    assert "Dash" in body["feature_label"]

    # ── Layer 2: economy_update WS frame with slot=bonus, used=True
    eu = ws.wait_for(
        "economy_update", timeout_ms=5000,
        predicate=lambda f: (
            f["data"].get("character_id") == pip["id"]
            and f["data"].get("slot") == "bonus"
        ),
    )
    assert eu["data"]["used"] is True, (
        f"Cunning Action should MARK the bonus slot used; got {eu['data']}"
    )

    # ── feature_used broadcast also fires — assert it lands ───────
    ws.wait_for(
        "feature_used", timeout_ms=3000,
        predicate=lambda f: (
            f["data"].get("character_id") == pip["id"]
            and "Cunning Action" in (f["data"].get("feature_name") or "")
            and "Dash" in (f["data"].get("feature_name") or "")
        ),
    )

    # ── Post-condition: bonus chip is now .used ───────────────────
    bonus_chip_after = tabletop.combatant_row("Pip Quickfingers").locator(
        '.econ-chip[data-slot="bonus"]'
    ).first
    expect(bonus_chip_after).to_have_class(re.compile(r"\bused\b"), timeout=3000)
