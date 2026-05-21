"""test_buff_install_decrement — Phase 3 (Level 2), commit K.

Validates the **buff duration tick-down** path on turn-end. Krieger
activates Rage (10-round buff). The GM clicks "Next ▶" to end his
turn. The client-side buff-tick logic in tabletop.html (~line 5311)
walks his buffs, decrements every duration_rounds by 1, drops any
that hit 0, and pushes the new state. The buff chip's duration
label should now read "9 rounds" instead of "10 rounds".

The tick is GM-driven + client-side: the GM's "Next" button click
handler does the math locally and pushes the new battle state via
``pushBattle()``. No server endpoint involved in the tick itself —
which is why this test asserts on the rendered DOM, not on a WS
broadcast (the server only sees the after-state via the PUT and
broadcasts ``battle_update``, which the GM client THEN IGNORES per
the v2.5.5 echo-loop guard).

Buffs tick when the OWNER's turn ends (``source_caster_id == cur.
id``). Rage is a self-buff so Krieger owns his own buff. Test
must therefore put Krieger as ``turn_index=0`` so his turn ends
on the first Next click.
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


KRIEGER_CID = "es_rage_tick_caster"


def test_krieger_rage_buff_ticks_on_turn_end(
    gm_context: BrowserContext,
    roster: dict,
):
    krieger = roster["Krieger Stonefist"]
    long_rest(krieger["id"])
    # Krieger at turn_index 0 so his turn is the current one — Next
    # ends his turn and ticks his buffs.
    combatants = [
        make_combatant(
            KRIEGER_CID,
            char_id=krieger["id"],
            name="Krieger Stonefist",
            hp_cur=58,
            hp_max=58,
            initiative=20,
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

    # ── Install Rage (duration_rounds = 10) ───────────────────────
    resp = post_use("use_rage", krieger["id"])
    assert resp.status_code == 200, resp.text
    # Wait for the buff_update broadcast so the GM page applies the
    # buff locally before we check the chip.
    ws.wait_for("buff_update", timeout_ms=5000)

    rage_chip = tabletop.combatant_row("Krieger Stonefist").locator(
        ".buff-chip"
    ).filter(has_text="Rage")
    expect(rage_chip).to_be_visible(timeout=3000)
    # Pre-tick duration: "10 rounds"
    expect(rage_chip).to_contain_text("10", timeout=3000)

    # ── Advance turn (Krieger's turn ends → buff ticks) ───────────
    # The Next button handler at tabletop.html:5290 runs the tick
    # synchronously inside the click handler, then calls pushBattle()
    # + renderBattle(). The DOM reflects the new state after the
    # click returns. Playwright auto-waits via expect().
    gm_page.locator("#battle-next-btn").click()

    # Post-tick: Rage chip now reads "9 rounds".
    # Re-locate the chip because renderBattle re-creates the DOM.
    rage_chip_after = tabletop.combatant_row("Krieger Stonefist").locator(
        ".buff-chip"
    ).filter(has_text="Rage")
    expect(rage_chip_after).to_be_visible(timeout=3000)
    expect(rage_chip_after).to_contain_text("9", timeout=3000)
    # And NOT the pre-tick value (defensive — guards against a
    # regression where the tick fires but renderBattle uses stale
    # data).
    chip_text = rage_chip_after.inner_text()
    assert "10 rounds" not in chip_text, (
        f"Rage chip still says '10 rounds' after turn-end tick: {chip_text!r}"
    )
