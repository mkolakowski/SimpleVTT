"""test_magnus_eldritch_blast — Warlock multi-beam cantrip PoC.

Phase 2 (commit G). Magnus Hexbinder (L5 Warlock) casts Eldritch
Blast — the only PHB cantrip that fires MULTIPLE attack rolls per
cast (1 base + 1 extra_beams at L5+). Each beam rolls 1d20 attack
vs target AC and 1d10 force damage on hit, independently.

Response carries ``auto_attack_beams: [{beam, total, hit, crit,
damage_rolled}, ...]`` (v2.40.0) — that's the multi-beam test
vector. The roll-log card RENDERS ONE pill aggregating the beams
(``auto_attack_hit = any_hit``, ``auto_attack_total = max(beam.
total)``, ``auto_attack_damage_rolled = sum(beam.damage_rolled)``);
per-beam detail lives only in the JSON payload. Layer 5's assertion
is therefore the headline attack pill, not per-beam pills — but
layer 2 still proves the per-beam data is present in the broadcast.
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


MAGNUS_CID = "es_magnus_eb_caster"
BANDIT_CID = "es_magnus_eb_target"
EB_INDEX = 0  # Magnus's spell list: 0 Eldritch Blast, ...


def test_magnus_eldritch_blast_multibeam(
    gm_context: BrowserContext,
    roster: dict,
    set_dice_seed,
):
    magnus = roster["Magnus Hexbinder"]
    # Cantrip uses no slot but long-rest insures pre-existing state.
    long_rest(magnus["id"])
    bandit_tmpl_id = bandit_template_id()
    combatants = [
        make_combatant(
            MAGNUS_CID,
            char_id=magnus["id"],
            name="Magnus Hexbinder",
            hp_cur=33,
            hp_max=33,
            initiative=11,
        ),
        make_combatant(
            BANDIT_CID,
            template_id=bandit_tmpl_id,
            name="Bandit Alpha",
            hp_cur=50,
            hp_max=50,
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
        magnus["id"],
        EB_INDEX,
        slot_level=0,
        class_slug="warlock",
        target_combatant_id=BANDIT_CID,
        target_name="Bandit Alpha",
    )

    # Layer 1: HTTP — 2 beams at L5
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    beams = body.get("auto_attack_beams") or []
    assert len(beams) == 2, f"expected 2 beams at L5 Warlock, got {len(beams)}"
    for b in beams:
        assert "total" in b
        assert "hit" in b
        assert "crit" in b
        if b["hit"]:
            min_dmg = 2 if b["crit"] else 1
            max_dmg = 20 if b["crit"] else 10
            assert min_dmg <= b["damage_rolled"] <= max_dmg

    # Layer 2: WS — auto_attack_beams forwarded
    frame = ws.wait_for("spell_cast", timeout_ms=5000)
    assert frame["data"]["spell_name"] == "Eldritch Blast"
    assert frame["data"]["caster_char_name"] == "Magnus Hexbinder"
    ws_beams = frame["data"].get("auto_attack_beams") or []
    assert len(ws_beams) == 2

    # Layer 3: toast
    toast = gm_page.locator(".roll-toast .rt-label").filter(has_text="Eldritch Blast").first
    expect(toast).to_be_visible(timeout=3000)

    # Layer 4: roll-log card
    gm_page.evaluate("window._openDrawerPanel('roll-log-drawer')")
    roll_log = RollLogPage(gm_page)
    card = roll_log.latest_spell_cast_card()
    expect(card).to_be_visible(timeout=3000)
    expect(card).to_contain_text("Eldritch Blast", timeout=3000)

    # Layer 5: aggregated headline attack pill — the card collapses
    # multi-beam down to one pill (any_hit drives chip class). Per-
    # beam detail is in the WS frame only (asserted at layer 2).
    if body["auto_attack_hit"]:
        expected_chip = "chip-crit" if body.get("auto_attack_crit") else "chip-hit"
    else:
        expected_chip = "chip-miss"
    pill = card.locator(f".result-pill.{expected_chip}").first
    expect(pill).to_be_visible(timeout=3000)
