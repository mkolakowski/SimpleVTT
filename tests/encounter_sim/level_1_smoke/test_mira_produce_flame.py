"""test_mira_produce_flame — Druid single-beam attack cantrip PoC.

Phase 2 (commit G). Mira Greenleaf casts Produce Flame — a single-
target attack-roll cantrip dealing fire damage. Same code path as
Eldritch Blast but with one beam, so the response carries the
flat ``auto_attack_*`` fields instead of ``auto_attack_beams``.
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


MIRA_CID = "es_mira_pf_caster"
BANDIT_CID = "es_mira_pf_target"
PRODUCE_FLAME_INDEX = 1  # Mira: 0 Druidcraft, 1 Produce Flame, ...


def test_mira_produce_flame_attack_cantrip(
    gm_context: BrowserContext,
    roster: dict,
    set_dice_seed,
):
    mira = roster["Mira Greenleaf"]
    long_rest(mira["id"])
    bandit_tmpl_id = bandit_template_id()
    combatants = [
        make_combatant(
            MIRA_CID,
            char_id=mira["id"],
            name="Mira Greenleaf",
            hp_cur=38,
            hp_max=38,
            initiative=12,
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
        mira["id"],
        PRODUCE_FLAME_INDEX,
        slot_level=0,
        class_slug="druid",
        target_combatant_id=BANDIT_CID,
        target_name="Bandit Alpha",
    )

    # Layer 1: HTTP — attack-roll cantrip uses auto_attack_* fields
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert isinstance(body["auto_attack_hit"], bool)
    assert body["auto_attack_total"] >= 1
    assert body["auto_attack_target_ac"] >= 8
    assert body["auto_attack_target_name"] == "Bandit Alpha"
    if body["auto_attack_hit"]:
        # Cantrip scaling: Produce Flame is 1d8 at L1-4, 2d8 at L5+.
        # Mira is L5 in the demo, so damage rolled in [2, 16].
        assert body["auto_attack_damage_rolled"] >= 1
        assert body["auto_attack_damage_type"] == "fire"
    else:
        assert body["auto_attack_damage_applied"] == 0

    # Layer 2: WS
    frame = ws.wait_for("spell_cast", timeout_ms=5000)
    assert frame["data"]["spell_name"] == "Produce Flame"
    assert frame["data"]["caster_char_name"] == "Mira Greenleaf"

    # Layer 3: toast
    toast = gm_page.locator(".roll-toast .rt-label").filter(has_text="Produce Flame").first
    expect(toast).to_be_visible(timeout=3000)

    # Layer 4: roll-log card
    gm_page.evaluate("window._openDrawerPanel('roll-log-drawer')")
    roll_log = RollLogPage(gm_page)
    card = roll_log.latest_spell_cast_card()
    expect(card).to_be_visible(timeout=3000)
    expect(card).to_contain_text("Produce Flame", timeout=3000)

    # Layer 5: attack-roll pill (chip-hit / chip-miss / chip-crit)
    # appendSpellCast renders one attack pill for non-beam, non-AoE
    # cantrips (tabletop.js ~line 2580: `cls = ... ? chip-crit :
    # chip-hit : chip-miss`).
    if body["auto_attack_hit"]:
        expected_chip = "chip-crit" if body.get("auto_attack_crit") else "chip-hit"
    else:
        expected_chip = "chip-miss"
    pill = card.locator(f".result-pill.{expected_chip}").first
    expect(pill).to_be_visible(timeout=3000)
