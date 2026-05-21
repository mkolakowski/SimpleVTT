"""test_alice_observes_hp_update — Phase 4 (Level 3), commit V.

**First player-driver test in the suite.** Closes the GM-driver
caveat that every Phase 1 / 2 PoC test has carried: the GM ignores
``battle_update`` broadcasts (echo-loop guard), so the strike PoCs
couldn't assert layer 6 of the plan's chain — "Target's HP bar in
``#init-tracker`` reflects damage" — on rendered DOM. This test
proves the assertion fires when driven by a **non-GM** (Alice,
who owns Pip Quickfingers).

The mechanism: ``PATCH /sheet-fields`` with ``hp.current`` causes
the server to broadcast ``character_hp_update`` (since v2.49.42 —
prior to that, PATCH only broadcast ``character_death_save`` on
status crossings, leaving HP-bar movement silent). Alice's client
(no IS_GM guard on the hp_update handler at tabletop.js:3102)
mutates ``window.battle.combatants[…]`` for the matching ``char_id``
and re-renders the init tracker.

Scenario:
  1. Seed battle with Pip (server-side AND in Alice's localStorage
     so her init IIFE picks her up on first paint).
  2. Open Alice's tabletop page → players panel.
  3. Pre-condition: Pip's HP in Alice's DOM reads "HP 35".
  4. GM PATCHes Pip's HP from 35 → 25 via ``apply_damage`` (which
     wraps PATCH /sheet-fields with damage semantics).
  5. Server broadcasts ``character_hp_update`` with the new HP.
  6. Alice's client mutates her local battle state + re-renders.
  7. Post-condition: Alice's DOM reads "HP 25".

History: pre-v2.49.42, this test had to drive damage through /attack
(Krieger swinging at Pip) with seeded dice + retry-on-miss because
PATCH /sheet-fields didn't broadcast HP changes. The v2.49.42 fix
landed the missing broadcast; this test was simplified at v2.49.45
to use the direct PATCH path — fewer moving pieces, fully
deterministic, no dice variance.

Note on DOM: Alice OWNS Pip so her init-entry renders (the
``IS_GM || hasCharDetail`` branch at tabletop.html:4998). But the
``.init-hp-cur`` input is GM-only — Alice gets the mini-header
text only. HP appears in ``.mini-header-sub`` as "Init N · HP
CUR / MAX". We assert against the rendered text.
"""
from __future__ import annotations

import re

from playwright.sync_api import BrowserContext, expect

from ...conftest import tabletop_url
from ...helpers.battle import (
    apply_damage,
    make_combatant,
    seed_battle,
    seed_battle_into_page,
)
from ...helpers.reset import long_rest
from ...helpers.ws import WSCollector


PIP_CID = "es_alice_pip"


def test_alice_sees_pip_hp_drop_on_damage(
    alice_context: BrowserContext,
    roster: dict,
):
    pip = roster["Pip Quickfingers"]
    # Long-rest Pip so her sheet HP starts at max. Prior tests
    # (e.g. test_massive_damage_instakill, test_drops_on_zero_hp)
    # can leave her sheet at 0 or 1, which would skew the
    # ``delta`` field on the broadcast (computed as new - pre,
    # where pre is the sheet's current).
    long_rest(pip["id"])

    combatants = [
        make_combatant(
            PIP_CID, char_id=pip["id"], name="Pip Quickfingers",
            hp_cur=35, hp_max=35, initiative=15,
        ),
    ]
    seed_battle(combatants)
    seed_battle_into_page(alice_context, combatants)

    alice_page = alice_context.new_page()
    ws = WSCollector(alice_page)
    ws.start()
    alice_page.goto(tabletop_url())
    alice_page.evaluate("window._openDrawerPanel('players-drawer')")

    pip_row = alice_page.locator(".init-entry").filter(
        has=alice_page.locator(".mini-header-name", has_text="Pip Quickfingers")
    ).first
    expect(pip_row).to_be_visible(timeout=5000)

    hp_label = pip_row.locator(".mini-header-sub").first
    # Pre-condition: HP 35 / 35.
    expect(hp_label).to_contain_text("HP", timeout=3000)
    expect(hp_label).to_contain_text("35", timeout=3000)

    # ── GM PATCHes Pip's HP down by 10 ────────────────────────────
    # v2.49.42 made PATCH /sheet-fields broadcast character_hp_update
    # for HP changes within "alive" (previously only fired on status
    # crossings). Deterministic — no dice, no retry-on-miss.
    resp = apply_damage(
        pip["id"], damage_amount=10, new_hp_current=25,
        damage_type="slashing",
    )
    assert resp.status_code == 200, resp.text

    # ── Layer 2: character_hp_update on Alice's WS ────────────────
    hp_frame = ws.wait_for(
        "character_hp_update", timeout_ms=5000,
        predicate=lambda f: f["data"].get("character_id") == pip["id"],
    )
    assert hp_frame["data"]["hp"]["current"] == 25
    # The source label distinguishes /attack from PATCH /sheet-fields.
    # Asserting on it pins which code path fired the broadcast.
    assert hp_frame["data"]["source"] == "sheet_patch"
    # Delta is new_current - pre_patch_current. Pre-patch was Pip's
    # max (33 in the demo seed, freshly restored via long_rest);
    # new is 25 → delta = 25 - 33 = -8. The exact value depends on
    # the demo seed's max HP for Pip; assert sign + plausibility.
    assert hp_frame["data"]["delta"] < 0, (
        f"PATCH HP down should produce negative delta; got {hp_frame['data']['delta']}"
    )

    # ── Layer 6: Alice's DOM reflects the new HP ─────────────────
    # The hp_update handler at tabletop.js:3102 mutates
    # window.battle.combatants + calls render(). The init-tracker
    # re-renders, the .mini-header-sub text shows the new HP.
    # Re-locate the label (renderBattle re-creates the DOM).
    pip_row_after = alice_page.locator(".init-entry").filter(
        has=alice_page.locator(".mini-header-name", has_text="Pip Quickfingers")
    ).first
    hp_label_after = pip_row_after.locator(".mini-header-sub").first
    expect(hp_label_after).to_contain_text("25", timeout=3000)
    # Defensive parse of "HP CUR / MAX" to rule out a false positive
    # where the max happens to equal the new HP value.
    label_text = hp_label_after.inner_text()
    cur_match = re.search(r"HP\s*(\d+)\s*/\s*(\d+)", label_text)
    assert cur_match, f"could not parse HP from {label_text!r}"
    cur = int(cur_match.group(1))
    assert cur == 25, f"current HP {cur} != expected 25"
