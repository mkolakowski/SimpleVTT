"""test_save_on_damage — Phase 4 (Level 3), commit Q.

Validates the **damage-triggered concentration save** path. When a
concentrating caster takes damage, the server fires a CON save
against DC = max(10, damage/2). On fail, the concentration buff is
dropped + a ``buff_update`` follows with ``removed_key``. On pass,
concentration holds.

Scenario:
  1. Magnus casts Hex on Pip → Hex buff installed on Magnus with
     ``concentration: True``.
  2. PATCH ``/sheet-fields`` damages Magnus by 10 HP (33 → 23).
  3. Server computes DC = max(10, 10/2) = 10 and rolls Magnus's CON
     save. Broadcasts ``concentration_save`` with the roll +
     pass/fail.
  4. Test asserts the broadcast shape regardless of outcome.
  5. On fail, asserts ``buff_update`` with ``removed_key="hex"``
     follows + Hex chip disappears from Magnus's row.

This is the complement to commit L's `test_concentration_lifecycle`
(install + manual DELETE end): here the END path is automatic,
triggered by the damage rule.
"""
from __future__ import annotations

from playwright.sync_api import BrowserContext, expect

from ...conftest import tabletop_url
from ...helpers.battle import (
    apply_damage,
    make_combatant,
    post_use,
    seed_battle,
    seed_battle_into_page,
)
from ...helpers.reset import long_rest
from ...helpers.ws import WSCollector
from ...pages.tabletop import TabletopPage


MAGNUS_CID = "es_conc_save_magnus"
PIP_CID = "es_conc_save_pip"


def test_concentration_save_fires_on_caster_damage(
    gm_context: BrowserContext,
    roster: dict,
):
    magnus = roster["Magnus Hexbinder"]
    pip = roster["Pip Quickfingers"]
    # Hex consumes a Pact slot — long-rest refills.
    long_rest(magnus["id"])

    combatants = [
        make_combatant(
            MAGNUS_CID, char_id=magnus["id"],
            name="Magnus Hexbinder", hp_cur=33, hp_max=33, initiative=15,
        ),
        make_combatant(
            PIP_CID, char_id=pip["id"],
            name="Pip Quickfingers", hp_cur=35, hp_max=35, initiative=12,
        ),
    ]
    seed_battle(combatants)
    seed_battle_into_page(gm_context, combatants)

    gm_page = gm_context.new_page()
    ws = WSCollector(gm_page)
    ws.start()
    gm_page.goto(tabletop_url())
    gm_page.evaluate("window._openDrawerPanel('players-drawer')")

    tabletop = TabletopPage(gm_page)
    expect(tabletop.combatant_row("Magnus Hexbinder")).to_be_visible(timeout=5000)

    # ── Install Hex on Pip ────────────────────────────────────────
    resp = post_use(
        "cast_hex", magnus["id"],
        extra={"target_character_id": pip["id"], "ability": "STR"},
    )
    assert resp.status_code == 200, resp.text
    ws.wait_for(
        "buff_update", timeout_ms=5000,
        predicate=lambda f: (
            f["data"].get("character_id") == magnus["id"]
            and any(b.get("key") == "hex" for b in f["data"].get("buffs") or [])
        ),
    )
    hex_chip = tabletop.combatant_row("Magnus Hexbinder").locator(
        ".buff-chip"
    ).filter(has_text="Hex")
    expect(hex_chip).to_be_visible(timeout=3000)

    # ── Damage Magnus → concentration save fires ──────────────────
    resp_dmg = apply_damage(
        magnus["id"], damage_amount=10, new_hp_current=23,
        damage_type="slashing",
    )
    assert resp_dmg.status_code == 200, resp_dmg.text

    # ── Layer 2: concentration_save broadcast ─────────────────────
    cs = ws.wait_for(
        "concentration_save", timeout_ms=5000,
        predicate=lambda f: f["data"].get("character_id") == magnus["id"],
    )
    assert cs["data"]["buff_key"] == "hex"
    assert cs["data"]["damage_amount"] == 10
    # DC = max(10, damage / 2) = max(10, 5) = 10.
    assert cs["data"]["dc"] == 10
    assert isinstance(cs["data"]["passed"], bool)

    # ── On fail, Hex drops; on pass, Hex remains ──────────────────
    # Both outcomes are valid (depend on Magnus's d20 + CON mod);
    # the test is self-consistent with the WS frame's `passed`
    # field, no hardcoded outcome.
    if not cs["data"]["passed"]:
        # Failed con save → buff_update broadcasts with removed_key.
        # Server may broadcast either the full new buff list OR a
        # diff-style {removed_key} frame depending on the path —
        # accept either by predicate.
        bu = ws.wait_for(
            "buff_update", timeout_ms=5000,
            predicate=lambda f: (
                f["data"].get("character_id") == magnus["id"]
                and (
                    f["data"].get("removed_key") == "hex"
                    or not any(b.get("key") == "hex" for b in f["data"].get("buffs") or [])
                )
            ),
        )
        # Chip should disappear from Magnus's row.
        hex_chip_after = tabletop.combatant_row("Magnus Hexbinder").locator(
            ".buff-chip"
        ).filter(has_text="Hex")
        expect(hex_chip_after).to_have_count(0, timeout=3000)
    else:
        # Passed con save → Hex chip stays on Magnus.
        expect(hex_chip).to_be_visible(timeout=3000)
