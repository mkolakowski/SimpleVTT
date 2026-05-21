"""test_pip_strike — Rogue weapon-attack PoC (Phase 2, third strike test).

Mirrors ``test_garrik_strike`` but driven by Pip Quickfingers (Rogue,
demo Lv 5). Same 6-layer assertion ladder — different PC, different
weapon (Shortsword, 1d20+6 attack, 1d6+3 piercing damage). Catches
weapon-attack regressions specific to the rogue sheet's attack
resolution path.

Sneak Attack uplift is deliberately NOT exercised here — that's a
separate ``test_pip_sneak_attack`` filed for later in Phase 2 because
it needs an additional "uplift" parameter in the POST body and
exercises a different code path. Keep this test minimal so it tracks
the regression class "vanilla rogue strike still works."

Architectural caveats apply (see ``test_garrik_strike.py`` docstring):
GM-as-driver means init-tracker DOM HP doesn't refresh; layer 6 reads
server response ``target_hp_after``.
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


PIP_CID = "es_pip_strike_caster"
BANDIT_CID = "es_pip_strike_target"


def test_pip_shortsword_strike_full_chain(
    gm_context: BrowserContext,
    roster: dict,
    set_dice_seed,
):
    """Shortsword strike on Bandit Alpha — 6-layer chain."""
    pip = roster["Pip Quickfingers"]
    combatants = [
        make_combatant(
            PIP_CID,
            char_id=pip["id"],
            name="Pip Quickfingers",
            hp_cur=35,
            hp_max=35,
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
    assert hp_before == 30

    set_dice_seed(42)
    resp = post_attack(
        pip["id"], attack_index=0, target_combatant_id=BANDIT_CID
    )

    # Layer 1: HTTP
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["attack_name"] == "Shortsword"
    assert body["damage_type"] == "piercing"
    # 1d20+6 → [7, 26]; 1d6+3 → [4, 9].
    assert 7 <= body["attack_total"] <= 26
    assert 4 <= body["damage_total"] <= 9

    # Layer 2: WS
    frame = ws.wait_for("weapon_attack", timeout_ms=5000)
    assert frame["data"]["attack_name"] == "Shortsword"
    assert frame["data"]["caster_char_name"] == "Pip Quickfingers"
    assert frame["data"]["target_combatant_id"] == BANDIT_CID

    # Layer 3: toast
    toast = gm_page.locator(".roll-toast .rt-label").filter(has_text="Shortsword").first
    expect(toast).to_be_visible(timeout=3000)

    # Layer 4: roll-log card
    gm_page.evaluate("window._openDrawerPanel('roll-log-drawer')")
    roll_log = RollLogPage(gm_page)
    card = roll_log.latest_weapon_attack_card()
    expect(card).to_be_visible(timeout=3000)
    expect(card).to_contain_text("Shortsword", timeout=3000)

    # Layer 5: damage pill
    assert_pill(card, chip_class="chip-damage")

    # Layer 6: server-side HP delta
    hit = frame["data"]["hit"]
    if hit:
        applied = body["damage_applied"]
        assert applied > 0
        assert body["target_hp_after"] == hp_before - applied
    else:
        assert body["damage_applied"] == 0
        assert body["target_hp_after"] == hp_before
