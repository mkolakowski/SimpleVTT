"""test_kael_strike — Monk Unarmed Strike vanilla PoC.

Phase 2 (commit H). Kael Brightleaf swings his Unarmed Strike (Martial
Arts d6) at Bandit Alpha. Vanilla weapon attack — no Stunning Strike
uplift here (filed for Phase 3/4 with the broader save-on-hit
condition family).
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
from ..helpers.ws import WSCollector
from ..pages.roll_log import RollLogPage
from ..pages.tabletop import TabletopPage


KAEL_CID = "es_kael_strike_caster"
BANDIT_CID = "es_kael_strike_target"


def test_kael_unarmed_strike_full_chain(
    gm_context: BrowserContext,
    roster: dict,
    set_dice_seed,
):
    kael = roster["Kael Brightleaf"]
    combatants = [
        make_combatant(
            KAEL_CID,
            char_id=kael["id"],
            name="Kael Brightleaf",
            hp_cur=38,
            hp_max=38,
            initiative=15,
        ),
        make_combatant(
            BANDIT_CID,
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
    hp_before = tabletop.combatant_hp("Bandit Alpha")

    set_dice_seed(42)
    resp = post_attack(kael["id"], attack_index=0, target_combatant_id=BANDIT_CID)

    # Layer 1
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["attack_name"] == "Unarmed Strike"
    # 1d20+7 → [8, 27]; 1d6+4 → [5, 10].
    assert 8 <= body["attack_total"] <= 27
    assert 5 <= body["damage_total"] <= 10

    # Layer 2
    frame = ws.wait_for("weapon_attack", timeout_ms=5000)
    assert frame["data"]["attack_name"] == "Unarmed Strike"
    assert frame["data"]["caster_char_name"] == "Kael Brightleaf"

    # Layer 3
    toast = gm_page.locator(".roll-toast .rt-label").filter(has_text="Unarmed Strike").first
    expect(toast).to_be_visible(timeout=3000)

    # Layer 4
    gm_page.evaluate("window._openDrawerPanel('roll-log-drawer')")
    card = RollLogPage(gm_page).latest_weapon_attack_card()
    expect(card).to_be_visible(timeout=3000)
    expect(card).to_contain_text("Unarmed Strike", timeout=3000)

    # Layer 5
    assert_pill(card, chip_class="chip-damage")

    # Layer 6
    if frame["data"]["hit"]:
        assert body["damage_applied"] > 0
        assert body["target_hp_after"] == hp_before - body["damage_applied"]
    else:
        assert body["damage_applied"] == 0
