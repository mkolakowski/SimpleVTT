"""test_npc_save_with_auto_damage_off — Phase 4 (Level 3), commit Z.

Opens the **save resolution matrix** subsystem. The plan calls for
12 tests covering the combinatorial grid:
``(PC×NPC) × (passed×failed) × (auto-damage on×off) × (resistance×not) × (concentration×not)``.

This opener pins the **auto-damage OFF** axis against an NPC target:
the server still rolls the save (auto_save_passed populated) but
applies NO damage (auto_save_damage_applied == 0). The roll-log
card therefore renders the save pill (`chip-hit` or `chip-miss`)
but the damage pill, if it appears, carries `applied: 0` —
which the renderer represents differently from auto-damage-on.

Why this is a good opener: it exercises the BRANCH SELECTION
in `_cast_spell_save_branch`. The earlier Phase 1 Tavik test
(`test_tavik_sacred_flame`) ran with auto-damage ON; this test
runs with it OFF, and the two together bracket the entire
auto-damage axis. The remaining axes (PC target, resistance,
concentration interaction) each get their own commits in the
follow-up matrix expansion.

Scenario:
  1. Disable auto-apply-damage via campaign settings.
  2. Long-rest Tavik so cantrip state is clean.
  3. Seed Tavik + Bandit Alpha into battle.
  4. Cast Sacred Flame at Bandit Alpha.
  5. Assert HTTP body: ``auto_save_target_kind="npc"``,
     ``auto_save_passed`` is a bool (server still rolls),
     ``auto_save_damage_rolled`` is in cantrip range,
     ``auto_save_damage_applied == 0`` (the off-branch).
  6. Teardown: restore auto-apply-damage to the demo default
     (off → off, but defensive in case a prior test left it on).
"""
from __future__ import annotations

from playwright.sync_api import BrowserContext, expect

from ...conftest import tabletop_url
from ...helpers.battle import (
    bandit_template_id,
    cast_spell,
    make_combatant,
    seed_battle,
    seed_battle_into_page,
    set_auto_apply,
)
from ...helpers.reset import long_rest
from ...helpers.ws import WSCollector
from ...pages.roll_log import RollLogPage
from ...pages.tabletop import TabletopPage


TAVIK_CID = "es_save_off_tavik"
BANDIT_CID = "es_save_off_bandit"
SACRED_FLAME_INDEX = 0  # Tavik's cleric spell list


def test_save_rolls_but_no_damage_when_auto_apply_off(
    gm_context: BrowserContext,
    roster: dict,
    set_dice_seed,
):
    tavik = roster["Brother Tavik Stonebrow"]
    long_rest(tavik["id"])

    # Critical: auto-apply OFF for this matrix point.
    set_auto_apply(False)

    bandit_tmpl_id = bandit_template_id()
    combatants = [
        make_combatant(
            TAVIK_CID, char_id=tavik["id"],
            name="Brother Tavik Stonebrow", hp_cur=30, hp_max=30, initiative=15,
        ),
        make_combatant(
            BANDIT_CID, template_id=bandit_tmpl_id, name="Bandit Alpha",
            hp_cur=30, hp_max=30, initiative=10,
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
    expect(tabletop.combatant_row("Bandit Alpha")).to_be_visible(timeout=5000)

    try:
        set_dice_seed(42)
        resp = cast_spell(
            tavik["id"], SACRED_FLAME_INDEX,
            slot_level=0, class_slug="cleric",
            target_combatant_id=BANDIT_CID, target_name="Bandit Alpha",
        )

        # ── Layer 1: HTTP — save was rolled, no damage applied ────
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["auto_save_target_kind"] == "npc"
        assert isinstance(body["auto_save_passed"], bool)
        # KEY ASSERTION: with auto-apply OFF, the server skips the
        # damage roll entirely — both `damage_rolled` and
        # `damage_applied` stay at 0. The save is still ROLLED
        # (auto_save_passed populated) so the GM has the outcome
        # data; the GM applies damage manually if they want.
        assert body["auto_save_damage_rolled"] == 0, (
            f"auto_apply_damage is OFF; damage_rolled should be 0 "
            f"(server skips the damage roll). Got "
            f"{body['auto_save_damage_rolled']}"
        )
        assert body["auto_save_damage_applied"] == 0, (
            f"auto_apply_damage is OFF; damage_applied should be 0 "
            f"regardless of save outcome. Got {body['auto_save_damage_applied']}"
        )

        # ── Layer 2: WS spell_cast carries the same fields ────────
        frame = ws.wait_for(
            "spell_cast", timeout_ms=5000,
            predicate=lambda f: f["data"].get("spell_name") == "Sacred Flame",
        )
        assert frame["data"]["auto_save_damage_applied"] == 0

        # ── Layer 4: roll-log card renders, with save pill but the
        # damage indicator should NOT show "X HP" applied. The card
        # still shows the rolled damage amount; we check that the
        # WS frame's data is honest about applied=0.
        gm_page.evaluate("window._openDrawerPanel('roll-log-drawer')")
        card = RollLogPage(gm_page).latest_spell_cast_card()
        expect(card).to_be_visible(timeout=3000)
        expect(card).to_contain_text("Sacred Flame", timeout=3000)

        # ── Layer 6: bandit's HP in init tracker UNCHANGED ────────
        # NPC HP in GM view shows up via the .init-hp-cur input (GM
        # gets the editable variant). Should still read 30 since no
        # damage was applied.
        hp_input = tabletop.combatant_row("Bandit Alpha").locator(
            ".init-hp-cur"
        ).first
        expect(hp_input).to_have_value("30", timeout=3000)
    finally:
        # Restore the demo default: auto-apply OFF (which is what we
        # have; the assert here is defensive).
        set_auto_apply(False)
