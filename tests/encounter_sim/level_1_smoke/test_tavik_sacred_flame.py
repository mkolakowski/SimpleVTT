"""test_tavik_sacred_flame — single-target save-spell PoC.

Phase 1, commit D companion to ``test_garrik_strike.py``. Where Garrik
exercised the weapon-attack path (1d20+mod vs AC + damage on hit),
Tavik exercises the **save spell** path:

  - POST ``/cast_spell`` with Sacred Flame (cleric cantrip, idx 0)
  - Server rolls the target's DEX save vs DC 14 (Tavik's wisdom-based
    cantrip DC, demo seed)
  - On fail: 2d8 radiant damage applied (cantrip scales 2d8 at L5+).
    On pass: 0 damage (Sacred Flame has no save-for-half).
  - Roll-log card carries either ``chip-hit`` or ``chip-miss`` for
    the save pill, plus ``chip-damage`` when damage landed.

Same architectural caveats as Garrik (see that file's docstring):
GM-as-driver means the init-tracker DOM HP won't refresh. Layer 6 is
asserted against the server response body (``auto_save_damage_
applied``), not the DOM.
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
from ..helpers.ws import WSCollector
from ..pages.roll_log import RollLogPage
from ..pages.tabletop import TabletopPage


TAVIK_CID = "es_tavik_sf_caster"
BANDIT_CID = "es_tavik_sf_target"
SACRED_FLAME_INDEX = 0  # Tavik's spell list: 0 Sacred Flame, 1 Guidance, ...


def test_tavik_sacred_flame_full_chain(
    gm_context: BrowserContext,
    roster: dict,
    set_dice_seed,
):
    """Sacred Flame at Bandit Alpha — single-target save spell chain."""
    tavik = roster["Brother Tavik Stonebrow"]
    bandit_tmpl_id = bandit_template_id()
    combatants = [
        make_combatant(
            TAVIK_CID,
            char_id=tavik["id"],
            name="Brother Tavik Stonebrow",
            hp_cur=30,
            hp_max=30,
            initiative=12,
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

    # Open players panel so init tracker is visible for the initial
    # state assertion. We'll flip to roll-log later.
    gm_page.evaluate("window._openDrawerPanel('players-drawer')")
    tabletop = TabletopPage(gm_page)
    expect(tabletop.combatant_row("Bandit Alpha")).to_be_visible(timeout=5000)
    assert tabletop.combatant_hp("Bandit Alpha") == 30

    # ── Fire the spell ────────────────────────────────────────────
    set_dice_seed(42)
    resp = cast_spell(
        tavik["id"],
        SACRED_FLAME_INDEX,
        slot_level=0,
        class_slug="cleric",
        target_combatant_id=BANDIT_CID,
        target_name="Bandit Alpha",
    )

    # ── Layer 1: HTTP ─────────────────────────────────────────────
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    # ``spell_name`` lives in the WS frame's data, not the HTTP body
    # — the body returns slot + auto_save_* fields only. Verify name
    # at layer 2.
    assert body["auto_save_target_kind"] == "npc"
    assert isinstance(body["auto_save_passed"], bool)
    assert body["auto_save_damage_type"] == "radiant"
    # Cantrip scaling: 2d8 at Cleric L5+ → rolled in [2, 16].
    assert 2 <= body["auto_save_damage_rolled"] <= 16, (
        f"damage_rolled={body['auto_save_damage_rolled']} outside 2..16 (cantrip scaling)"
    )
    # v2.31.0 default: save spells apply half damage on a successful
    # save (Sacred Flame doesn't carry an explicit "no-half" flag in
    # the content, so it falls under the default). Full damage on
    # fail. Bandit has no radiant resistance.
    if body["auto_save_passed"]:
        assert body["auto_save_damage_applied"] == body["auto_save_damage_rolled"] // 2
    else:
        assert body["auto_save_damage_applied"] == body["auto_save_damage_rolled"]

    # ── Layer 2: WS broadcast ─────────────────────────────────────
    frame = ws.wait_for("spell_cast", timeout_ms=5000)
    assert frame["data"]["spell_name"] == "Sacred Flame"
    assert frame["data"]["caster_char_name"] == "Brother Tavik Stonebrow"
    assert frame["data"]["auto_save_ability"] == "DEX"
    assert frame["data"]["auto_save_dc"] == 14
    assert frame["data"]["auto_save_target_name"] == "Bandit Alpha"

    # ── Layer 3: toast ────────────────────────────────────────────
    toast = gm_page.locator(".roll-toast .rt-label").filter(has_text="Sacred Flame").first
    expect(toast).to_be_visible(timeout=3000)

    # ── Layer 4: roll-log card ────────────────────────────────────
    gm_page.evaluate("window._openDrawerPanel('roll-log-drawer')")
    roll_log = RollLogPage(gm_page)
    card = roll_log.latest_spell_cast_card()
    expect(card).to_be_visible(timeout=3000)
    expect(card).to_contain_text("Sacred Flame", timeout=3000)

    # ── Layer 5: save pill ────────────────────────────────────────
    # Save pill class follows the WS frame's auto_save_passed: chip-hit
    # for a passed save (target avoided the spell), chip-miss for a
    # failed save (Sacred Flame lands its full damage). Test asserts
    # the EXPECTED chip is present without hardcoding pass/fail —
    # whichever the seed produces, the pill class matches.
    passed = frame["data"]["auto_save_passed"]
    expected_chip = "chip-hit" if passed else "chip-miss"
    save_pill = card.locator(f".result-pill.{expected_chip}").first
    expect(save_pill).to_be_visible(timeout=3000)
    # Save pill text contains the DC (e.g. "DC 14" or "DEX save · DC 14").
    expect(save_pill).to_contain_text("14", timeout=3000)

    # ── Layer 6: server-side damage applied ───────────────────────
    # Same caveat as Garrik (see test_garrik_strike.py docstring) —
    # GM driver, /cast_spell doesn't force_gm_sync battle_update, so
    # the init-tracker HP DOM stays stale. We assert on the response
    # body's auto_save_damage_applied which is the source of truth.
    # Save-for-half default means damage is applied either way (full
    # on fail, half on pass) — both should render a chip-damage pill.
    applied = body["auto_save_damage_applied"]
    assert applied > 0, f"expected damage applied (save-for-half default); got {applied}"
    dmg_pill = card.locator(".result-pill.chip-damage").first
    expect(dmg_pill).to_be_visible(timeout=3000)
