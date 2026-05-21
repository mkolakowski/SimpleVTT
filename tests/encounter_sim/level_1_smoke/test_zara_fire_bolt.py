"""test_zara_fire_bolt — Sorcerer single-beam attack cantrip PoC.

Phase 2 (commit H). Zara Emberfire (L5 Sorcerer) casts Fire Bolt at
Bandit Alpha — same shape as Mira's Produce Flame test but with a
different class (Draconic Bloodline sorcerer, demo Lv 5) and damage
type (fire vs fire — same actually, but the cast resolver path is
the sorcerer's, not the druid's).
"""
from __future__ import annotations

from playwright.sync_api import BrowserContext, expect

from ..conftest import tabletop_url
from ..helpers.battle import (
    bandit_template_id,
    cast_spell,
    make_combatant,
    seed_battle,
    seed_battle_into_page,
    set_auto_apply,
)
from ..helpers.reset import long_rest
from ..helpers.ws import WSCollector
from ..pages.roll_log import RollLogPage
from ..pages.tabletop import TabletopPage


ZARA_CID = "es_zara_fb_caster"
BANDIT_CID = "es_zara_fb_target"
FIRE_BOLT_INDEX = 0  # Zara's spell list: 0 Fire Bolt, ...


def test_zara_fire_bolt_attack_cantrip(
    gm_context: BrowserContext,
    roster: dict,
    set_dice_seed,
):
    zara = roster["Zara Emberfire"]
    long_rest(zara["id"])
    bandit_tmpl_id = bandit_template_id()
    combatants = [
        make_combatant(
            ZARA_CID,
            char_id=zara["id"],
            name="Zara Emberfire",
            hp_cur=37,
            hp_max=37,
            initiative=13,
        ),
        make_combatant(
            BANDIT_CID,
            template_id=bandit_tmpl_id,
            name="Bandit Alpha",
            hp_cur=30,
            hp_max=30,
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

    set_dice_seed(42)
    resp = cast_spell(
        zara["id"],
        FIRE_BOLT_INDEX,
        slot_level=0,
        class_slug="sorcerer",
        target_combatant_id=BANDIT_CID,
        target_name="Bandit Alpha",
    )

    # Layer 1
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert isinstance(body["auto_attack_hit"], bool)
    assert body["auto_attack_target_name"] == "Bandit Alpha"
    if body["auto_attack_hit"]:
        assert body["auto_attack_damage_rolled"] >= 1
        assert body["auto_attack_damage_type"] == "fire"
    else:
        assert body["auto_attack_damage_applied"] == 0

    # Layer 2
    frame = ws.wait_for("spell_cast", timeout_ms=5000)
    assert frame["data"]["spell_name"] == "Fire Bolt"
    assert frame["data"]["caster_char_name"] == "Zara Emberfire"

    # Layer 3
    toast = gm_page.locator(".roll-toast .rt-label").filter(has_text="Fire Bolt").first
    expect(toast).to_be_visible(timeout=3000)

    # Layer 4
    gm_page.evaluate("window._openDrawerPanel('roll-log-drawer')")
    card = RollLogPage(gm_page).latest_spell_cast_card()
    expect(card).to_be_visible(timeout=3000)
    expect(card).to_contain_text("Fire Bolt", timeout=3000)

    # Layer 5
    if body["auto_attack_hit"]:
        expected_chip = "chip-crit" if body.get("auto_attack_crit") else "chip-hit"
    else:
        expected_chip = "chip-miss"
    expect(card.locator(f".result-pill.{expected_chip}").first).to_be_visible(timeout=3000)
