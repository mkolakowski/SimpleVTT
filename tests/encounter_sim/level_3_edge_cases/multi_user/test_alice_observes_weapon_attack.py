"""test_alice_observes_weapon_attack — Phase 4 (Level 3), commit W.

Player-driver variant of the Phase 1 `test_garrik_strike`. Where
the original asserted layer-6 against the response body (GM-driver
caveat: GM ignores echo broadcasts so DOM updates couldn't be
verified), this test proves a non-GM observer (Alice) sees:

  1. ``weapon_attack`` broadcast on her WS.
  2. ``.weapon-atk-card`` element rendered in her roll-log drawer.
  3. ``.result-pill.chip-damage`` inside the card.
  4. The card carries the weapon name + damage type + caster name.

The broadcast / DOM-render path is the same one that v2.49.4
shipped a regression in (broadcast OK, canvas render broken). This
test covers the roll-log-card render side of that same broadcast.

Driven via httpx `post_attack` from the GM side client; Alice's
browser WATCHES. The split-driver pattern is what unblocks every
future "did this broadcast reach non-GM clients?" assertion.
"""
from __future__ import annotations

from playwright.sync_api import BrowserContext, expect

from ...conftest import tabletop_url
from ...helpers.assert_pill import assert_pill
from ...helpers.battle import (
    make_combatant,
    post_attack,
    seed_battle,
    seed_battle_into_page,
    set_auto_apply,
)
from ...helpers.ws import WSCollector
from ...pages.roll_log import RollLogPage


GARRIK_CID = "es_alice_obs_garrik"
BANDIT_CID = "es_alice_obs_bandit"


def test_alice_sees_garrik_weapon_attack_card(
    alice_context: BrowserContext,
    roster: dict,
    set_dice_seed,
):
    garrik = roster["Garrik Ironside"]
    combatants = [
        make_combatant(
            GARRIK_CID, char_id=garrik["id"], name="Garrik Ironside",
            hp_cur=49, hp_max=49, initiative=15,
        ),
        make_combatant(
            BANDIT_CID, name="Bandit Alpha", hp_cur=30, hp_max=30, initiative=10,
        ),
    ]
    seed_battle(combatants)
    seed_battle_into_page(alice_context, combatants)
    set_auto_apply(True)

    alice_page = alice_context.new_page()
    ws = WSCollector(alice_page)
    ws.start()
    alice_page.goto(tabletop_url())

    # ── GM fires Garrik's Greatsword at the bandit ────────────────
    set_dice_seed(42)
    resp = post_attack(
        garrik["id"], attack_index=0, target_combatant_id=BANDIT_CID,
    )
    assert resp.status_code == 200, resp.text

    # ── Layer 2: weapon_attack on Alice's WS ──────────────────────
    frame = ws.wait_for(
        "weapon_attack", timeout_ms=5000,
        predicate=lambda f: (
            f["data"].get("attack_name") == "Greatsword"
            and f["data"].get("caster_char_name") == "Garrik Ironside"
        ),
    )
    assert frame["data"]["target_name"] == "Bandit Alpha"
    assert frame["data"]["damage_type"] == "slashing"

    # ── Layer 4 + 5: card in ALICE's roll-log + damage pill ───────
    alice_page.evaluate("window._openDrawerPanel('roll-log-drawer')")
    card = RollLogPage(alice_page).latest_weapon_attack_card()
    expect(card).to_be_visible(timeout=3000)
    expect(card).to_contain_text("Greatsword", timeout=3000)
    expect(card).to_contain_text("Garrik Ironside", timeout=3000)
    assert_pill(card, chip_class="chip-damage")
