"""test_concentration_lifecycle — Phase 3 (Level 2), commit L.

Validates the **concentration install + manual-end** path:

  1. Magnus casts Hex on Pip via ``POST /cast_hex``. The server
     installs a Hex buff on Magnus with ``concentration: True`` and
     a ``target_character_id`` pointing at Pip; broadcasts
     ``feature_used`` + ``buff_update``.
  2. The init tracker shows a "Hex" chip in Magnus's row.
  3. ``DELETE /concentration/{magnus_id}`` ends the
     ``ConcentrationEffect`` row. Broadcasts ``concentration_update``
     with ``ended: True``.
  4. v2.49.41: the DELETE endpoint also calls ``_remove_buff`` for
     every concentration-tagged buff on the caster, which fires a
     ``buff_update`` AND ``_drop_paired_concentration_buffs`` for
     any target-side condition buffs (Paralyzed via Hold Person,
     Frightened via Fear, …). Pre-v2.49.41 the chip stayed on the
     caster's row until the GM × button cleared it; this test
     pinned that limitation. With the fix landed, the test now
     verifies the chip DISAPPEARS after DELETE.

This file is the regression test for the v2.49.41 fix: a DELETE
that leaves the chip behind would surface here as the
``to_have_count(0)`` assertion failing.
"""
from __future__ import annotations

from playwright.sync_api import BrowserContext, expect

from ..conftest import tabletop_url
from ..helpers.battle import (
    end_concentration,
    make_combatant,
    post_use,
    seed_battle,
    seed_battle_into_page,
)
from ..helpers.reset import long_rest
from ..helpers.ws import WSCollector
from ..pages.tabletop import TabletopPage


MAGNUS_CID = "es_conc_magnus"
PIP_CID = "es_conc_pip"


def test_hex_install_and_concentration_end_lifecycle(
    gm_context: BrowserContext,
    roster: dict,
):
    magnus = roster["Magnus Hexbinder"]
    pip = roster["Pip Quickfingers"]
    # Hex consumes a Pact slot (L3 only at Warlock L5). Long-rest so
    # the slot is available regardless of prior test order.
    long_rest(magnus["id"])

    combatants = [
        make_combatant(
            MAGNUS_CID,
            char_id=magnus["id"],
            name="Magnus Hexbinder",
            hp_cur=33,
            hp_max=33,
            initiative=15,
        ),
        make_combatant(
            PIP_CID,
            char_id=pip["id"],
            name="Pip Quickfingers",
            hp_cur=35,
            hp_max=35,
            initiative=12,
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

    # Pre-check: no Hex chip yet.
    hex_chip = tabletop.combatant_row("Magnus Hexbinder").locator(
        ".buff-chip"
    ).filter(has_text="Hex")
    assert hex_chip.count() == 0, "Hex shouldn't be installed before cast"

    # ── Step 1: install Hex via /cast_hex ─────────────────────────
    resp = post_use(
        "cast_hex", magnus["id"],
        extra={"target_character_id": pip["id"], "ability": "STR"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["ability"] == "STR"
    assert body["slot_level"] == 3  # Magnus only has L3 Pact slots

    # ── Layer 2: WS ───────────────────────────────────────────────
    fu = ws.wait_for("feature_used", timeout_ms=5000)
    assert fu["data"]["source"] == "hex"
    assert fu["data"]["ability"] == "STR"

    bu = ws.wait_for(
        "buff_update", timeout_ms=5000,
        predicate=lambda f: f["data"].get("character_id") == magnus["id"],
    )
    hex_buff = next((b for b in bu["data"]["buffs"] if b["key"] == "hex"), None)
    assert hex_buff is not None, f"no hex buff in {bu['data']['buffs']}"
    assert hex_buff["concentration"] is True
    assert hex_buff["target_character_id"] == pip["id"]

    # ── Step 2: Hex chip visible in Magnus's row ──────────────────
    expect(hex_chip).to_be_visible(timeout=3000)
    expect(hex_chip).to_contain_text("Hex", timeout=3000)

    # ── Step 3: end concentration via DELETE ──────────────────────
    resp_end = end_concentration(magnus["id"])
    assert resp_end.status_code == 200, resp_end.text

    # ── Layer 2: concentration_update with ended:True ─────────────
    cu = ws.wait_for(
        "concentration_update", timeout_ms=5000,
        predicate=lambda f: f["data"].get("character_id") == magnus["id"],
    )
    assert cu["data"].get("ended") is True, f"expected ended:True, got {cu['data']}"

    # ── Layer 4 (v2.49.41 fix): buff_update fires with hex removed
    # AND the chip disappears from Magnus's row. Pre-v2.49.41 these
    # assertions would fail because end_concentration only deleted
    # the ConcentrationEffect row without touching the buff list.
    ws.wait_for(
        "buff_update", timeout_ms=5000,
        predicate=lambda f: (
            f["data"].get("character_id") == magnus["id"]
            and not any(
                b.get("key") == "hex" for b in f["data"].get("buffs") or []
            )
        ),
    )
    hex_chip_after = tabletop.combatant_row("Magnus Hexbinder").locator(
        ".buff-chip"
    ).filter(has_text="Hex")
    expect(hex_chip_after).to_have_count(0, timeout=3000)
