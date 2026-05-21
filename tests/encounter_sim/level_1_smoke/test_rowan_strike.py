"""test_rowan_strike — Ranger Longbow vanilla PoC.

Phase 2 (commit H, final Phase 2 test). Rowan Quickbow (L5 Ranger)
shoots his Longbow at Bandit Alpha. Vanilla weapon attack — no
Hunter's Mark concentration buff install in this test (filed for
Phase 3 with the concentration-lifecycle test family).
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


ROWAN_CID = "es_rowan_strike_caster"
BANDIT_CID = "es_rowan_strike_target"


def test_rowan_longbow_strike_full_chain(
    gm_context: BrowserContext,
    roster: dict,
    set_dice_seed,
):
    rowan = roster["Rowan Quickbow"]
    combatants = [
        make_combatant(
            ROWAN_CID,
            char_id=rowan["id"],
            name="Rowan Quickbow",
            hp_cur=44,
            hp_max=44,
            initiative=14,
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
    resp = post_attack(rowan["id"], attack_index=0, target_combatant_id=BANDIT_CID)

    # Layer 1
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["attack_name"] == "Longbow"
    # 1d20+9 → [10, 29]; 1d8+4 → [5, 12].
    assert 10 <= body["attack_total"] <= 29
    assert 5 <= body["damage_total"] <= 12

    # Layer 2
    frame = ws.wait_for("weapon_attack", timeout_ms=5000)
    assert frame["data"]["attack_name"] == "Longbow"
    assert frame["data"]["caster_char_name"] == "Rowan Quickbow"

    # Layer 3
    toast = gm_page.locator(".roll-toast .rt-label").filter(has_text="Longbow").first
    expect(toast).to_be_visible(timeout=3000)

    # Layer 4
    gm_page.evaluate("window._openDrawerPanel('roll-log-drawer')")
    card = RollLogPage(gm_page).latest_weapon_attack_card()
    expect(card).to_be_visible(timeout=3000)
    expect(card).to_contain_text("Longbow", timeout=3000)

    # Layer 5
    assert_pill(card, chip_class="chip-damage")

    # Layer 6 — init-tracker DOM HP (v2.49.40 fix; see test_garrik_strike).
    gm_page.evaluate("window._openDrawerPanel('players-drawer')")
    if frame["data"]["hit"]:
        assert body["damage_applied"] > 0
        gm_page.wait_for_timeout(200)
        assert tabletop.combatant_hp("Bandit Alpha") == hp_before - body["damage_applied"]
    else:
        assert body["damage_applied"] == 0
        assert tabletop.combatant_hp("Bandit Alpha") == hp_before
