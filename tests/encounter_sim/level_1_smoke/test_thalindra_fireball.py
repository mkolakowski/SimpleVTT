"""test_thalindra_fireball — AoE save-spell PoC.

Phase 1, commit D companion to ``test_garrik_strike`` and
``test_tavik_sacred_flame``. Thalindra exercises the **AoE save**
path: one ``/cast_spell`` POST with ``target_combatant_ids=[3
bandits]``, server loops the save + damage application per target,
response carries ``auto_save_targets`` with 3 per-target outcomes,
the WS broadcast carries the same, and the rendered roll-log card
shows three per-target pills + one ``Σ total`` damage pill.

Same architectural caveats apply (see ``test_garrik_strike.py``
docstring): GM driver means the bandits' init-tracker HP DOM stays
stale; layer 6 reads from the response body per-target outcomes
which are the source of truth for the rendered card pills.
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


THAL_CID = "es_thal_fireball_caster"
BANDIT_CIDS = [
    "es_thal_fireball_b1",
    "es_thal_fireball_b2",
    "es_thal_fireball_b3",
]
BANDIT_NAMES = ["Bandit Alpha", "Bandit Beta", "Bandit Gamma"]
FIREBALL_INDEX = 7  # Thalindra's spell list: 0 Fire Bolt, ..., 7 Fireball.


def test_thalindra_fireball_aoe_full_chain(
    gm_context: BrowserContext,
    roster: dict,
    set_dice_seed,
):
    """Fireball at 3 bandits — AoE save spell, multi-target chain."""
    thal = roster["Thalindra Moonwhisper"]
    # Fireball consumes a L3 slot; long-rest Thalindra so the slot is
    # available regardless of prior test order. Filed for Phase 2: a
    # suite-wide autouse ``long_rest_everyone`` fixture.
    long_rest(thal["id"])
    bandit_tmpl_id = bandit_template_id()
    combatants = [
        make_combatant(
            THAL_CID,
            char_id=thal["id"],
            name="Thalindra Moonwhisper",
            hp_cur=24,
            hp_max=24,
            initiative=15,
        ),
    ]
    for cid, name, init in zip(BANDIT_CIDS, BANDIT_NAMES, [10, 9, 8]):
        combatants.append(
            make_combatant(
                cid,
                template_id=bandit_tmpl_id,
                name=name,
                hp_cur=50,
                hp_max=50,
                initiative=init,
            )
        )

    seed_battle(combatants)
    seed_battle_into_page(gm_context, combatants)
    set_auto_apply(True)

    gm_page = gm_context.new_page()
    ws = WSCollector(gm_page)
    ws.start()
    gm_page.goto(tabletop_url())

    gm_page.evaluate("window._openDrawerPanel('players-drawer')")
    tabletop = TabletopPage(gm_page)
    # All three bandits should render in init.
    for name in BANDIT_NAMES:
        expect(tabletop.combatant_row(name)).to_be_visible(timeout=5000)

    # ── Fire the spell ────────────────────────────────────────────
    set_dice_seed(42)
    resp = cast_spell(
        thal["id"],
        FIREBALL_INDEX,
        slot_level=3,
        class_slug="wizard",
        target_combatant_ids=BANDIT_CIDS,
    )

    # ── Layer 1: HTTP ─────────────────────────────────────────────
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    targets = body.get("auto_save_targets") or []
    assert len(targets) == 3, f"expected 3 per-target outcomes, got {len(targets)}: {targets}"
    names = {t["target_name"] for t in targets}
    assert names == set(BANDIT_NAMES), f"unexpected target names: {names}"
    for t in targets:
        # 8d6 fire — both save-for-half and full-on-fail should be > 0.
        assert t["damage_applied"] > 0, f"{t['target_name']}: damage_applied={t['damage_applied']}"
        assert t["damage_type"] == "fire"
        assert isinstance(t["passed"], bool)
        # ``rolled`` is the bandit's DEX save (1d20+dex_mod), not the
        # spell damage. Bandit DEX is 12 (mod +1), so [2, 21].
        assert 2 <= t["rolled"] <= 21, f"{t['target_name']}: save roll={t['rolled']}"

    # ── Layer 2: WS broadcast ─────────────────────────────────────
    frame = ws.wait_for("spell_cast", timeout_ms=5000)
    assert frame["data"]["spell_name"] == "Fireball"
    assert frame["data"]["caster_char_name"] == "Thalindra Moonwhisper"
    assert frame["data"]["spell_level"] == 3
    # Per-target outcomes mirror the HTTP body.
    ws_targets = frame["data"].get("auto_save_targets") or []
    assert len(ws_targets) == 3
    assert {t["target_name"] for t in ws_targets} == set(BANDIT_NAMES)

    # ── Layer 3: toast ────────────────────────────────────────────
    toast = gm_page.locator(".roll-toast .rt-label").filter(has_text="Fireball").first
    expect(toast).to_be_visible(timeout=3000)

    # ── Layer 4: roll-log card ────────────────────────────────────
    gm_page.evaluate("window._openDrawerPanel('roll-log-drawer')")
    roll_log = RollLogPage(gm_page)
    card = roll_log.latest_spell_cast_card()
    expect(card).to_be_visible(timeout=3000)
    expect(card).to_contain_text("Fireball", timeout=3000)

    # ── Layer 5: per-target save pills + Σ total damage pill ──────
    # appendSpellCast renders one ``per-target-pill`` per target with
    # chip-hit (passed) or chip-miss (failed), plus a single chip-damage
    # pill carrying the Σ total (sum across all targets). 3 targets →
    # at least 3 per-target pills.
    per_target_pills = card.locator(".result-pill.per-target-pill")
    expect(per_target_pills.first).to_be_visible(timeout=3000)
    assert per_target_pills.count() >= 3, (
        f"expected ≥3 per-target pills (one per bandit); got {per_target_pills.count()}"
    )
    # The Σ damage pill always renders for AoE damage spells.
    sigma_dmg = card.locator(".result-pill.chip-damage").first
    expect(sigma_dmg).to_be_visible(timeout=3000)

    # ── Layer 6: server-side per-target damage applied ────────────
    # GM driver caveat applies (see test_garrik_strike.py); we check
    # the response body's per-target damage_applied, which is the
    # source of truth that drives the per-target pill values.
    total_applied = sum(t["damage_applied"] for t in targets)
    assert total_applied > 0, "every bandit should have taken damage from 8d6 Fireball"
