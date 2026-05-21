"""test_alice_observes_hp_update — Phase 4 (Level 3), commit V.

**First player-driver test in the suite.** Closes the GM-driver
caveat that every Phase 1 / 2 PoC test has carried: the GM ignores
`battle_update` broadcasts (echo-loop guard), so the strike PoCs
couldn't assert layer 6 of the plan's chain — "Target's HP bar in
``#init-tracker`` reflects damage" — on rendered DOM. This test
proves the assertion fires when driven by a **non-GM** (Alice,
who owns Pip Quickfingers).

The mechanism: when damage applies to a PC via the `/sheet-fields`
PATCH path (or any other route that calls `_apply_hp_change`), the
server broadcasts `character_hp_update`. Alice's client (no IS_GM
guard on this handler, see tabletop.js:3102) mutates
``window.battle.combatants[…]`` for the matching `char_id` and
calls `render()` — which re-paints the init tracker with the new
HP.

Scenario:
  1. Seed battle with Pip + Bandit Alpha (server-side AND in
     Alice's localStorage so her init IIFE picks them up).
  2. Open Alice's tabletop page → players panel.
  3. Pre-condition: Pip's HP in the player-view DOM reads 35.
  4. GM applies 10 damage to Pip via `apply_damage`.
  5. Server broadcasts `character_hp_update` with the new HP.
  6. Alice's client mutates her local battle state + re-renders.
  7. Post-condition: Pip's HP in the player-view DOM reads 25.

Filed in commit J as the first non-GM helper; this is the first
test exercising the full player-driver path: Alice's WS receives
broadcasts, Alice's DOM updates, the test asserts on her view.

Note: Alice's player view of the init tracker uses a different
DOM shape from the GM view. The GM gets `.init-entry` with
`.init-hp-cur` input field; the player gets `.init-row` with an
`.init-name` span and an `.init-hp` HP-threshold label. This test
reads the HP threshold label (one of "Bloodied", "Wounded", etc.)
from Alice's view — or, where she owns the PC and gets the editable
init-entry, the `.init-hp-cur` input.
"""
from __future__ import annotations

from playwright.sync_api import BrowserContext, expect

from ...conftest import tabletop_url
from ...helpers.battle import (
    make_combatant,
    post_attack,
    seed_battle,
    seed_battle_into_page,
    set_auto_apply,
)
from ...helpers.ws import WSCollector


PIP_CID = "es_alice_pip"
KRIEGER_CID = "es_alice_krieger"


def test_alice_sees_pip_hp_drop_on_damage(
    alice_context: BrowserContext,
    roster: dict,
    set_dice_seed,
):
    pip = roster["Pip Quickfingers"]
    krieger = roster["Krieger Stonefist"]

    # Krieger attacks Pip — friendly fire works through the same
    # /attack pipeline, exercises ``_apply_damage_to_combatant``,
    # which broadcasts ``character_hp_update`` because Pip is a PC.
    # Direct PATCH /sheet-fields would broadcast ``character_death
    # _save`` only on status change — wrong path for this test's
    # purpose (we want HP-bar movement without crossing into dying).
    combatants = [
        make_combatant(
            KRIEGER_CID, char_id=krieger["id"], name="Krieger Stonefist",
            hp_cur=58, hp_max=58, initiative=15,
        ),
        make_combatant(
            PIP_CID, char_id=pip["id"], name="Pip Quickfingers",
            hp_cur=35, hp_max=35, initiative=10,
        ),
    ]
    seed_battle(combatants)
    seed_battle_into_page(alice_context, combatants)
    set_auto_apply(True)

    alice_page = alice_context.new_page()
    ws = WSCollector(alice_page)
    ws.start()
    alice_page.goto(tabletop_url())
    alice_page.evaluate("window._openDrawerPanel('players-drawer')")

    # Alice OWNS Pip so her init-entry renders (IS_GM || hasCharDetail
    # branch at tabletop.html:4998). But the ``.init-hp-cur`` input
    # is GM-only — Alice gets the mini-header text only. HP appears
    # in ``.mini-header-sub`` as "Init N · HP CUR / MAX". We assert
    # against the rendered text rather than an input value.
    pip_row = alice_page.locator(".init-entry").filter(
        has=alice_page.locator(".mini-header-name", has_text="Pip Quickfingers")
    ).first
    expect(pip_row).to_be_visible(timeout=5000)

    hp_label = pip_row.locator(".mini-header-sub").first
    # Pre-condition: HP 35 / 35.
    expect(hp_label).to_contain_text("HP", timeout=3000)
    expect(hp_label).to_contain_text("35", timeout=3000)

    # ── GM fires Krieger's Greataxe at Pip via /attack ────────────
    # /attack invokes ``_apply_damage_to_combatant`` which broadcasts
    # ``character_hp_update`` ONLY when damage actually applies
    # (hit + non-zero damage). Seed the dice so Krieger's d20 lands
    # a hit against Pip's AC; without the seed, a miss skips the
    # broadcast and the test flakes ~30% of the time.
    set_dice_seed(7)
    resp = post_attack(
        krieger["id"], attack_index=0, target_combatant_id=PIP_CID,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    if body.get("hit") is False:
        # Seed produced a miss — retry with a different seed. The
        # seed sequence is deterministic but specific values
        # producing hits depend on the resolver's exact RNG advance
        # pattern. This is a one-shot retry, not a flake.
        set_dice_seed(2)
        resp = post_attack(
            krieger["id"], attack_index=0, target_combatant_id=PIP_CID,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("hit") is True, (
            f"both seeds missed — Krieger's +5 attack vs Pip's AC should hit "
            f"on at least one of 7/2; got hits={body.get('hit')}"
        )

    # ── Layer 2: character_hp_update on Alice's WS ────────────────
    hp_frame = ws.wait_for(
        "character_hp_update", timeout_ms=5000,
        predicate=lambda f: f["data"].get("character_id") == pip["id"],
    )
    new_hp = int(hp_frame["data"]["hp"]["current"])
    # Pip starts at 35. Krieger's Greataxe is 1d12+3 (Lv5 Barbarian
    # has +3 STR mod), so damage is in [4, 15]. Pip's HP should drop
    # to 35 - damage_applied — anywhere between 20 and 31 (or higher
    # if the attack missed; we check below).
    assert 0 <= new_hp <= 35, f"unexpected new HP: {new_hp}"

    # ── Layer 6: Alice's DOM reflects the new HP ─────────────────
    # The hp_update handler at tabletop.js:3102 mutates
    # window.battle.combatants + calls render(). The init-tracker
    # re-renders, the .mini-header-sub text shows the new HP.
    # Re-locate the label (renderBattle re-creates the DOM).
    pip_row_after = alice_page.locator(".init-entry").filter(
        has=alice_page.locator(".mini-header-name", has_text="Pip Quickfingers")
    ).first
    hp_label_after = pip_row_after.locator(".mini-header-sub").first
    expect(hp_label_after).to_contain_text(str(new_hp), timeout=3000)
    # Defensive: parse the "HP CUR / MAX" pattern from the label
    # to rule out a false positive where the max happens to equal
    # the new HP value.
    import re
    label_text = hp_label_after.inner_text()
    cur_match = re.search(r"HP\s*(\d+)\s*/\s*(\d+)", label_text)
    assert cur_match, f"could not parse HP from {label_text!r}"
    cur = int(cur_match.group(1))
    assert cur == new_hp, f"current HP {cur} != broadcast {new_hp}"
