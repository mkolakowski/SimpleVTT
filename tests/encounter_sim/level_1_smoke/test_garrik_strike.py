"""test_garrik_strike — first PoC test of the encounter-simulation
suite (Phase 1, commit C).

Drives Garrik through one Greatsword strike on a pre-seeded "Bandit
Alpha" combatant, then asserts on the full chain from the plan's
7-layer assertion ladder (see ``docs/plans/encounter-sim-test-
suite.md`` § "Per-test assertion chain"):

  1. HTTP /attack         → 200 + response body shape
  2. WS weapon_attack     → ``data.attack_name`` etc.
  3. Toast .roll-toast    → contains "Greatsword"
  4. Roll-log .roll-card  → newest is .weapon-atk-card
  5. Damage pill          → .result-pill.chip-damage in the card
  6. Init-tracker DOM HP reflects the damage applied (v2.49.40 fix
     enables this — the bandit's row HP input shows the post-damage
     value, not just the response body)

Layer 7 (buff list) isn't applicable to a vanilla weapon strike;
asserted on by buff-installing tests later in Phase 1/2.

v2.49.40 closes the GM-driver caveat
-------------------------------------
Pre-v2.49.40, ``/attack`` broadcast ``battle_update`` for NPC damage
WITHOUT the ``force_gm_sync: True`` flag. The GM client (per the
v2.5.5 echo-loop guard at tabletop.html:5543) ignored those
broadcasts, so the bandit's HP in the init tracker stayed at the
pre-damage value even though the server applied damage and the
card text showed "30 → 19 HP". The original v2.49.16 version of
this test had to assert layer 6 against the response body's
``target_hp_after``, with a docstring caveat explaining why the
real DOM assertion couldn't run.

v2.49.40 added the missing ``force_gm_sync`` flag, so the GM
client now receives + applies the NPC-damage broadcast — the
DOM-HP assertion works. This test now asserts directly on the
init-tracker's ``.init-hp-cur`` input value, the proper layer-6
contract from the plan.

Driving mechanism
-----------------
The attack is fired via HTTP ``POST /attack`` (helper:
``helpers.battle.post_attack``), NOT via clicking the
``.atk-strike`` button on Garrik's sheet. Reasoning: the regression
class this suite was created to catch is "broadcast OK but DOM /
canvas render broken" (the v2.49.4 skull bug from the plan's intro).
The click-path is already covered by ``tests/harness_ui/test_attack_
toast.py``. Filed for a later commit: layer the UI click on top
once the simpler HTTP-driven flow is stable.

Determinism
-----------
``set_dice_seed(42)`` is called right before the POST so the dice
RNG produces the same sequence in CI. The hit/miss outcome is read
back from the WS frame's ``data.hit`` field — the test asserts
self-consistent behavior (hit ⇒ HP drops; miss ⇒ HP stays) rather
than hardcoding an exact total, so the test survives a future seed
change without a fix-up commit.
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


# Synthetic combatant IDs scoped to this file. Prefixed with ``es_``
# (encounter sim) so they don't collide with the ``tok_`` IDs in
# ``tests/harness/test_attack_auto_damage.py``.
GARRIK_CID = "es_garrik_strike_caster"
BANDIT_CID = "es_garrik_strike_target"


def test_garrik_greatsword_strike_full_chain(
    gm_context: BrowserContext,
    roster: dict,
    set_dice_seed,
):
    """End-to-end: Greatsword strike on Bandit Alpha.

    Touches all 6 visible-outcome layers from the plan.
    """
    garrik = roster["Garrik Ironside"]
    combatants = [
        make_combatant(
            GARRIK_CID,
            char_id=garrik["id"],
            name="Garrik Ironside",
            hp_cur=49,
            hp_max=49,
            initiative=12,
        ),
        make_combatant(
            BANDIT_CID,
            name="Bandit Alpha",
            hp_cur=30,
            hp_max=30,
            initiative=10,
        ),
    ]

    # ── Step 1: seed battle state on both sides ────────────────────
    # Server side so /attack can resolve target_combatant_id; GM page
    # side (via localStorage init script) because the GM client treats
    # localStorage as authoritative and ignores battle_update WS
    # broadcasts (tabletop.html:5543 echo-loop guard). Both go down
    # BEFORE the page opens so the IIFE finds the seeded state.
    seed_battle(combatants)
    seed_battle_into_page(gm_context, combatants)
    set_auto_apply(True)

    # ── Step 2: open the GM tabletop + install the WS collector ───
    # WSCollector must be started BEFORE ``goto()`` — Playwright's
    # ``page.on("websocket")`` only fires for sockets opened AFTER
    # the listener is registered.
    gm_page = gm_context.new_page()
    ws = WSCollector(gm_page)
    ws.start()
    gm_page.goto(tabletop_url())

    # The right drawer hosts both the init tracker AND the roll log
    # but only one panel is open at a time (last-used persists in
    # localStorage). Open the players panel explicitly so the init-
    # tracker entries are visible for layer-6 assertions; we'll flip
    # to the roll-log panel below for layer-4/5. ``_openDrawerPanel``
    # is exposed by the tabletop IIFE at v2.48.2 and is available
    # by the time goto's ``load`` event fires.
    gm_page.evaluate("window._openDrawerPanel('players-drawer')")

    # The bandit's init-entry should render from the seeded localStorage
    # battle state. Playwright auto-waits; if it never shows, the test
    # fails here with a clear "still not visible" error, not a confusing
    # later assertion miss.
    tabletop = TabletopPage(gm_page)
    expect(tabletop.combatant_row("Bandit Alpha")).to_be_visible(timeout=5000)

    hp_before = tabletop.combatant_hp("Bandit Alpha")
    assert hp_before == 30, f"seed_battle put hp_cur=30 but UI reads {hp_before}"

    # ── Step 3: seed dice + fire the attack ───────────────────────
    set_dice_seed(42)
    resp = post_attack(
        garrik["id"], attack_index=0, target_combatant_id=BANDIT_CID
    )

    # ── Layer 1: HTTP response ────────────────────────────────────
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["attack_name"] == "Greatsword"
    assert body["damage_type"] == "slashing"
    # 1d20+7 → [8, 27]. 2d6+4 damage → [6, 16]. Both ranges should
    # always hold regardless of seed; tighter values are a fragility.
    assert 8 <= body["attack_total"] <= 27, f"attack_total={body['attack_total']}"
    assert 6 <= body["damage_total"] <= 16, f"damage_total={body['damage_total']}"

    # ── Layer 2: WS broadcast ─────────────────────────────────────
    frame = ws.wait_for("weapon_attack", timeout_ms=5000)
    assert frame["data"]["attack_name"] == "Greatsword"
    assert frame["data"]["caster_char_name"] == "Garrik Ironside"
    assert frame["data"]["damage_type"] == "slashing"
    assert frame["data"]["target_combatant_id"] == BANDIT_CID
    assert frame["data"]["target_name"] == "Bandit Alpha"
    # hit can be True or False depending on the seeded attack_total
    # vs the bandit's AC; both are valid outcomes for this test.
    assert frame["data"]["hit"] in (True, False)

    # ── Layer 3: toast ────────────────────────────────────────────
    # ``.roll-toast`` is rendered by app/static/roll_toast.js. Two
    # toasts fire (attack + damage). We just need ONE matching one.
    toast = gm_page.locator(".roll-toast .rt-label").filter(has_text="Greatsword").first
    expect(toast).to_be_visible(timeout=3000)

    # ── Layer 4: roll-log card ────────────────────────────────────
    # Flip the right drawer over to the roll-log panel so the
    # ``#roll-list`` card is visible. The card was rendered when the
    # weapon_attack WS arrived; we just couldn't see it under the
    # players-drawer panel.
    gm_page.evaluate("window._openDrawerPanel('roll-log-drawer')")
    roll_log = RollLogPage(gm_page)
    card = roll_log.latest_weapon_attack_card()
    expect(card).to_be_visible(timeout=3000)
    expect(card).to_contain_text("Greatsword", timeout=3000)

    # ── Layer 5: damage pill ──────────────────────────────────────
    # ``chip-damage`` always renders when ``damage_total`` is set, hit
    # or miss (line 3502 of tabletop.js). We don't try to match the
    # exact text since the seed can change.
    assert_pill(card, chip_class="chip-damage")

    # ── Layer 6: init-tracker DOM HP reflects the damage ──────────
    # v2.49.40 fix: /attack's NPC-damage broadcast now carries
    # force_gm_sync: True, so the GM client applies the new HP to
    # its local battle state and re-renders. The init-tracker HP
    # input picks up the new value.
    #
    # Pre-v2.49.40: this assertion was impossible because the GM
    # client ignored the battle_update broadcast under the v2.5.5
    # echo-loop guard. The fallback was asserting on the response
    # body's ``target_hp_after``; that's been removed now that the
    # DOM path actually works.
    hit = frame["data"]["hit"]
    # Flip back to the players panel so the init tracker is visible.
    gm_page.evaluate("window._openDrawerPanel('players-drawer')")
    if hit:
        damage_applied = body["damage_applied"]
        assert damage_applied > 0, f"hit but damage_applied={damage_applied}"
        # Wait for the GM's local state + re-render to settle. The
        # echo-loop-bypass + render is synchronous after the WS
        # event but Playwright's frame lifecycle needs a tick.
        gm_page.wait_for_timeout(200)
        hp_after_dom = tabletop.combatant_hp("Bandit Alpha")
        assert hp_after_dom == hp_before - damage_applied, (
            f"init-tracker DOM HP {hp_after_dom} doesn't match expected "
            f"{hp_before - damage_applied} (hp_before={hp_before}, "
            f"damage_applied={damage_applied}). v2.49.40 fix may have "
            f"regressed — verify force_gm_sync still on the NPC-damage "
            f"battle_update broadcast."
        )
    else:
        assert body["damage_applied"] == 0
        # No damage → no broadcast → DOM unchanged.
        hp_after_dom = tabletop.combatant_hp("Bandit Alpha")
        assert hp_after_dom == hp_before
