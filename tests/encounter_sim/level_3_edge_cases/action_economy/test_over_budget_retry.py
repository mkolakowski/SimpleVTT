"""test_over_budget_retry — Phase 4 (Level 3), commit U.

Completes the action-economy gate trilogy alongside:
  - commit J's `test_action_economy_strict_mode` (strict gate BLOCKS).
  - commit R's `test_action_surge_refunds_chip` (REFUND path).

This test exercises the **retry-with-override** path: a non-GM
player who hits a used action slot gets a 409 over_budget, the
client opens its Layer B confirm modal, the player clicks
"Confirm", the client retries with ``override: true``, and the
server proceeds — broadcasting the weapon-attack with
``over_budget: True`` so the roll-log card renders the v2.6.1
Layer C audit badge (visible to everyone).

Scenario:
  1. Strict mode OFF (the demo default; the test pairs with
     commit J's strict-on variant).
  2. Pre-mark Pip's action slot used.
  3. Alice POSTs `/attack` with `override=false` → 409.
  4. Alice POSTs `/attack` with `override=true` → 200, broadcast
     carries `over_budget=True`.
  5. The GM page's roll-log card for the attack carries an
     ``.over-budget-badge`` element.

Tests the "audit trail" promise of the v2.6.1 design: even when
the gate is bypassed, the override is visible to the rest of the
table.
"""
from __future__ import annotations

from playwright.sync_api import BrowserContext, expect

from ...conftest import tabletop_url
from ...helpers.battle import (
    make_combatant,
    post_attack_as_player,
    seed_battle,
    seed_battle_into_page,
    set_strict_action_economy,
)
from ...helpers.ws import WSCollector
from ...pages.roll_log import RollLogPage
from ...pages.tabletop import TabletopPage


PIP_CID = "es_retry_pip"
BANDIT_CID = "es_retry_bandit"


def test_over_budget_retry_with_override_lands_audit_badge(
    gm_context: BrowserContext,
    roster: dict,
):
    pip = roster["Pip Quickfingers"]

    # Defensive: ensure strict mode is OFF (the demo default). A prior
    # aborted test that left strict on would invert this test's
    # expectations — explicitly set off so the override path actually
    # bypasses the gate.
    set_strict_action_economy(False)

    # Pre-mark Pip's action slot used so the FIRST attack hits the gate.
    pip_combatant = make_combatant(
        PIP_CID, char_id=pip["id"], name="Pip Quickfingers",
        hp_cur=35, hp_max=35, initiative=15,
    )
    pip_combatant["economy"]["action"] = True
    combatants = [
        pip_combatant,
        make_combatant(
            BANDIT_CID, name="Bandit Alpha", hp_cur=30, hp_max=30, initiative=10,
        ),
    ]
    seed_battle(combatants)
    seed_battle_into_page(gm_context, combatants)

    gm_page = gm_context.new_page()
    ws = WSCollector(gm_page)
    ws.start()
    gm_page.goto(tabletop_url())

    tabletop = TabletopPage(gm_page)
    gm_page.evaluate("window._openDrawerPanel('players-drawer')")
    expect(tabletop.combatant_row("Pip Quickfingers")).to_be_visible(timeout=5000)

    try:
        # ── Step 1: Alice fires WITHOUT override → 409 ────────────
        resp_blocked = post_attack_as_player(
            "demo-alice@example.com", "demopass",
            character_id=pip["id"],
            attack_index=0,
            target_combatant_id=BANDIT_CID,
            override=False,
        )
        assert resp_blocked.status_code == 409, (
            f"expected 409 over_budget on first try (strict OFF); "
            f"got {resp_blocked.status_code}: {resp_blocked.text}"
        )
        body_blocked = resp_blocked.json()
        assert body_blocked.get("error") == "over_budget"
        # ``strict: False`` so the client modal shows Confirm.
        assert body_blocked.get("strict") in (False, None)

        # ── Step 2: Alice retries WITH override → 200 ─────────────
        resp_ok = post_attack_as_player(
            "demo-alice@example.com", "demopass",
            character_id=pip["id"],
            attack_index=0,
            target_combatant_id=BANDIT_CID,
            override=True,
        )
        assert resp_ok.status_code == 200, (
            f"override retry should proceed (strict OFF); got "
            f"{resp_ok.status_code}: {resp_ok.text}"
        )

        # ── Layer 2: weapon_attack with over_budget=True ──────────
        frame = ws.wait_for(
            "weapon_attack", timeout_ms=5000,
            predicate=lambda f: (
                f["data"].get("caster_char_name") == "Pip Quickfingers"
            ),
        )
        assert frame["data"].get("over_budget") is True, (
            f"override retry should broadcast over_budget=True for audit; "
            f"got {frame['data']}"
        )
        assert frame["data"].get("over_budget_slot") == "action"

        # ── Layer 5: audit badge in the roll-log card ─────────────
        gm_page.evaluate("window._openDrawerPanel('roll-log-drawer')")
        card = RollLogPage(gm_page).latest_weapon_attack_card()
        expect(card).to_be_visible(timeout=3000)
        badge = card.locator(".over-budget-badge").first
        expect(badge).to_be_visible(timeout=3000)
        # Badge text contains the slot name + "Manual override" preamble.
        expect(badge).to_contain_text("Manual override", timeout=3000)
        expect(badge).to_contain_text("action", timeout=3000)
    finally:
        # Restore strict mode setting to its baseline (already off).
        set_strict_action_economy(False)
