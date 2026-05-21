"""test_krieger_rage — Barbarian Rage feature-use PoC.

Phase 2 (commit F). Krieger activates Rage via ``POST /use_rage``.
Exercises the **feature-use** code path (separate from /attack and
/cast_spell):

  - HTTP response carries ``damage_bonus``, ``duration_rounds``,
    ``buff_installed``, ``remaining`` slot count.
  - Three WS broadcasts fire: ``feature_used`` (the use-of-the-
    feature event), ``resource_update`` (rage slot pool dec'd),
    ``buff_update`` (rage buff installed on Krieger's combatant).
  - Roll-log gets a feature-used card.
  - Krieger's init-tracker row shows the new "Rage" buff chip — and
    here the GM CAN see it because the ``buff_update`` handler in
    tabletop.html has NO IS_GM guard (unlike the ``battle_update``
    handler that gated layer 6 of the strike PoCs).

So this is the first Phase 1/2 test whose layer 7 assertion (buff
list visible in the init tracker) actually fires on rendered DOM.
"""
from __future__ import annotations

from playwright.sync_api import BrowserContext, expect

from ..conftest import tabletop_url
from ..helpers.battle import (
    make_combatant,
    post_use,
    seed_battle,
    seed_battle_into_page,
)
from ..helpers.reset import long_rest
from ..helpers.ws import WSCollector
from ..pages.tabletop import TabletopPage


KRIEGER_CID = "es_krieger_rage_caster"


def test_krieger_rage_installs_buff(
    gm_context: BrowserContext,
    roster: dict,
):
    krieger = roster["Krieger Stonefist"]
    # Rage charges refresh on long rest; ensure the pool is full so a
    # prior test that spent all 3 doesn't 409 here.
    long_rest(krieger["id"])

    combatants = [
        make_combatant(
            KRIEGER_CID,
            char_id=krieger["id"],
            name="Krieger Stonefist",
            hp_cur=58,
            hp_max=58,
            initiative=10,
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
    expect(tabletop.combatant_row("Krieger Stonefist")).to_be_visible(timeout=5000)

    # Pre-check: no Rage buff chip yet.
    rage_chip = tabletop.combatant_row("Krieger Stonefist").locator(
        ".buff-chip"
    ).filter(has_text="Rage")
    assert rage_chip.count() == 0, "rage shouldn't be installed before use_rage"

    # ── Fire the feature ──────────────────────────────────────────
    resp = post_use("use_rage", krieger["id"])

    # Layer 1: HTTP
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["damage_bonus"] == 2  # Lv 5 Barbarian
    assert body["duration_rounds"] == 10
    assert body["buff_installed"] is True
    assert body["max"] == 3
    assert isinstance(body["remaining"], int) and body["remaining"] >= 0

    # Layer 2: WS — three frames, in any order
    fu = ws.wait_for("feature_used", timeout_ms=5000)
    assert fu["data"]["source"] == "rage"
    assert "Rage" in fu["data"]["feature_name"]

    ru = ws.wait_for("resource_update", timeout_ms=5000)
    assert ru["data"]["key"] == "rage"
    assert ru["data"]["current"] == body["remaining"]

    bu = ws.wait_for("buff_update", timeout_ms=5000)
    assert bu["data"]["character_id"] == krieger["id"]
    buffs = bu["data"]["buffs"]
    assert any(b.get("key") == "rage" for b in buffs), f"no rage buff in {buffs}"
    rage = next(b for b in buffs if b.get("key") == "rage")
    assert rage["name"] == "Rage"
    assert rage["duration_rounds"] == 10
    assert rage["duration_max"] == 10
    assert rage["effects"]["melee_str_damage_bonus"] == 2

    # Layer 7: buff chip appears in Krieger's init-tracker row.
    # Unlike battle_update, the buff_update handler in tabletop.html
    # does NOT gate on IS_GM, so the chip renders for the GM driver.
    expect(rage_chip).to_be_visible(timeout=3000)
    expect(rage_chip).to_contain_text("Rage", timeout=3000)
    # Duration label format: "10 rounds" (tabletop.html ~5100).
    expect(rage_chip).to_contain_text("10", timeout=3000)
