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

Note: the DELETE endpoint **does not** drop paired buffs. The
``_drop_paired_concentration_buffs`` helper is only invoked on
concentration SWAP (a new conc spell replaces the old) — see
tabletop_routes.py:433. Manually ending via DELETE leaves the Hex
buff on Magnus's combatant.buffs list; the GM clears it via the
buff-chip × button if they care. So this test asserts on the
``concentration_update`` broadcast, not on the chip disappearing.

Filed for separate commits:
  - Concentration-swap (cast a new conc spell → old drops + paired
    buffs drop). The harness already covers the back-end shape;
    a UI variant adds the chip-removed assertion.
  - Damage-triggered concentration save (Magnus takes damage →
    /concentration/{cid}/tick fires save → on fail buff drops).
    Needs HP-change mechanics on Magnus.
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
