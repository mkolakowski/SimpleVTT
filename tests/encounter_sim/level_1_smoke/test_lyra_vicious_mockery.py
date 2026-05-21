"""test_lyra_vicious_mockery — Bard save-cantrip PoC (Phase 2).

Mirrors ``test_tavik_sacred_flame`` but driven by Lyra Sunstrider
(Bard, demo Lv 6) casting Vicious Mockery — a WIS-save cantrip
dealing psychic damage with a save-for-half (v2.31.0 default). Lyra
scales the cantrip to 2d4 at L5+, so damage rolled in [2, 8].
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


LYRA_CID = "es_lyra_vm_caster"
BANDIT_CID = "es_lyra_vm_target"
VM_INDEX = 0  # Lyra's spell list: 0 Vicious Mockery, 1 Mage Hand, ...


def test_lyra_vicious_mockery_full_chain(
    gm_context: BrowserContext,
    roster: dict,
    set_dice_seed,
):
    """Vicious Mockery at Bandit Alpha — single-target save cantrip."""
    lyra = roster["Lyra Sunstrider"]
    # Cantrip uses no slot, but long-rest is cheap insurance against
    # any preceding test leaving Lyra in a degraded state (e.g.
    # exhaustion from a future Phase 2 test). Cantrips themselves
    # don't deplete; this is forward-protection.
    long_rest(lyra["id"])
    bandit_tmpl_id = bandit_template_id()
    combatants = [
        make_combatant(
            LYRA_CID,
            char_id=lyra["id"],
            name="Lyra Sunstrider",
            hp_cur=40,
            hp_max=40,
            initiative=14,
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
        lyra["id"],
        VM_INDEX,
        slot_level=0,
        class_slug="bard",
        target_combatant_id=BANDIT_CID,
        target_name="Bandit Alpha",
    )

    # Layer 1: HTTP
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["auto_save_target_kind"] == "npc"
    assert isinstance(body["auto_save_passed"], bool)
    assert body["auto_save_damage_type"] == "psychic"
    # Cantrip scaling: 2d4 at Bard L5+ → [2, 8].
    assert 2 <= body["auto_save_damage_rolled"] <= 8, (
        f"damage_rolled={body['auto_save_damage_rolled']} outside 2..8"
    )
    if body["auto_save_passed"]:
        assert body["auto_save_damage_applied"] == body["auto_save_damage_rolled"] // 2
    else:
        assert body["auto_save_damage_applied"] == body["auto_save_damage_rolled"]

    # Layer 2: WS
    frame = ws.wait_for("spell_cast", timeout_ms=5000)
    assert frame["data"]["spell_name"] == "Vicious Mockery"
    assert frame["data"]["caster_char_name"] == "Lyra Sunstrider"
    assert frame["data"]["auto_save_ability"] == "WIS"
    # Server computes DC from caster mods (8 + prof + CHA mod), not
    # from the attack-list ``save_dc: 14`` field — so the DC depends
    # on Lyra's seed-time CHA. Assert plausibility (8..20) and use
    # the actual value below.
    dc = frame["data"]["auto_save_dc"]
    assert isinstance(dc, int) and 8 <= dc <= 20, f"unexpected DC={dc}"
    assert frame["data"]["auto_save_target_name"] == "Bandit Alpha"

    # Layer 3: toast
    toast = gm_page.locator(".roll-toast .rt-label").filter(has_text="Vicious Mockery").first
    expect(toast).to_be_visible(timeout=3000)

    # Layer 4: roll-log card
    gm_page.evaluate("window._openDrawerPanel('roll-log-drawer')")
    roll_log = RollLogPage(gm_page)
    card = roll_log.latest_spell_cast_card()
    expect(card).to_be_visible(timeout=3000)
    expect(card).to_contain_text("Vicious Mockery", timeout=3000)

    # Layer 5: save pill matched to WS passed value + damage pill
    passed = frame["data"]["auto_save_passed"]
    save_pill = card.locator(
        f".result-pill.{'chip-hit' if passed else 'chip-miss'}"
    ).first
    expect(save_pill).to_be_visible(timeout=3000)
    expect(save_pill).to_contain_text(str(dc), timeout=3000)
    dmg_pill = card.locator(".result-pill.chip-damage").first
    expect(dmg_pill).to_be_visible(timeout=3000)

    # Layer 6: server-side damage applied (save-for-half default)
    assert body["auto_save_damage_applied"] > 0
