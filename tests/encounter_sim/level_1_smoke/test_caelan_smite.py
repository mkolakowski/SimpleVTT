"""test_caelan_smite — Paladin Strike + Divine Smite uplift PoC.

Phase 2 (commit F). Sir Caelan swings his Longsword AND declares
Divine Smite via the ``bonus_damage`` + ``spend_spell_slot`` uplift
params on ``/attack``. Exercises the uplift code path that didn't
fire in the earlier strike PoCs:

  - ``spend_spell_slot: {class_slug:"paladin", level:1}`` consumes a
    paladin L1 slot.
  - ``bonus_damage: "2d8"`` (the 5e Smite L1 yield) rolls a separate
    damage parcel; server returns ``bonus_damage_total`` in [2, 16].
  - The roll-log card renders a ``chip-buff`` pill labelled "Divine
    Smite +N" alongside the base damage pill.

Same architectural caveats as Phase 1 PoCs apply.
"""
from __future__ import annotations

from playwright.sync_api import BrowserContext, expect

from ..conftest import tabletop_url
from ..helpers.assert_pill import assert_pill
from ..helpers.battle import (
    make_combatant,
    post_attack,
    seed_battle,
    seed_battle_into_page,
    set_auto_apply,
)
from ..helpers.reset import long_rest
from ..helpers.ws import WSCollector
from ..pages.roll_log import RollLogPage
from ..pages.tabletop import TabletopPage


CAELAN_CID = "es_caelan_smite_caster"
BANDIT_CID = "es_caelan_smite_target"


def test_caelan_longsword_smite_full_chain(
    gm_context: BrowserContext,
    roster: dict,
    set_dice_seed,
):
    caelan = roster["Sir Caelan Lightbringer"]
    # Smite spends a paladin L1 slot; long-rest so the pool is full.
    long_rest(caelan["id"])
    combatants = [
        make_combatant(
            CAELAN_CID,
            char_id=caelan["id"],
            name="Sir Caelan Lightbringer",
            hp_cur=44,
            hp_max=44,
            initiative=13,
        ),
        make_combatant(
            BANDIT_CID,
            name="Bandit Alpha",
            hp_cur=40,
            hp_max=40,
            initiative=10,
        ),
    ]

    seed_battle(combatants)
    seed_battle_into_page(gm_context, combatants)
    set_auto_apply(True)

    gm_page = gm_context.new_page()
    ws = WSCollector(gm_page)
    ws.start()
    gm_page.goto(tabletop_url())

    gm_page.evaluate("window._openDrawerPanel('players-drawer')")
    tabletop = TabletopPage(gm_page)
    expect(tabletop.combatant_row("Bandit Alpha")).to_be_visible(timeout=5000)
    hp_before = tabletop.combatant_hp("Bandit Alpha")

    set_dice_seed(42)
    resp = post_attack(
        caelan["id"],
        attack_index=0,
        target_combatant_id=BANDIT_CID,
        bonus_damage="2d8",
        bonus_damage_label="Divine Smite",
        spend_spell_slot={"class_slug": "paladin", "level": 1},
    )

    # Layer 1: HTTP — base attack + smite parcel + slot spend
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["bonus_damage_label"] == "Divine Smite"
    # 2d8 → [2, 16].
    assert 2 <= body["bonus_damage_total"] <= 16, (
        f"bonus_damage_total={body['bonus_damage_total']} outside 2..16"
    )
    assert body["slot_spent_class"] == "paladin"
    assert body["slot_spent_level"] == 1

    # Layer 2: WS — same fields broadcast
    frame = ws.wait_for("weapon_attack", timeout_ms=5000)
    assert frame["data"]["bonus_damage_label"] == "Divine Smite"
    assert frame["data"]["slot_spent_class"] == "paladin"
    assert frame["data"]["slot_spent_level"] == 1

    # Layer 3: toast (just one of the attack/damage/smite toasts)
    toast = gm_page.locator(".roll-toast .rt-label").filter(
        has_text=caelan["name"].split()[0]
    ).first
    expect(toast).to_be_visible(timeout=3000)

    # Layer 4: roll-log card
    gm_page.evaluate("window._openDrawerPanel('roll-log-drawer')")
    roll_log = RollLogPage(gm_page)
    card = roll_log.latest_weapon_attack_card()
    expect(card).to_be_visible(timeout=3000)
    # Card contains both the weapon name AND the Divine Smite label.
    expect(card).to_contain_text("Divine Smite", timeout=3000)

    # Layer 5: base damage pill + smite bonus pill
    assert_pill(card, chip_class="chip-damage")
    # The bonus parcel renders as ``chip-buff`` labelled "✨ Divine
    # Smite +N" (tabletop.js line ~3515). One pill per uplift.
    smite_pill = card.locator(".result-pill.chip-buff").filter(has_text="Divine Smite").first
    expect(smite_pill).to_be_visible(timeout=3000)

    # Layer 6: server-side HP delta (base + smite damage on hit)
    hit = frame["data"]["hit"]
    if hit:
        assert body["damage_applied"] > 0
        # damage_applied carries the combined total (base + smite).
        assert body["target_hp_after"] == hp_before - body["damage_applied"]
    else:
        # On miss: smite slot is STILL spent (5e RAW), but damage is 0.
        assert body["damage_applied"] == 0
