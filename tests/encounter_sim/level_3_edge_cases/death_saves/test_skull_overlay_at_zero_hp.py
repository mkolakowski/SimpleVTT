"""test_skull_overlay_at_zero_hp — Phase 4 (Level 3), commit O.

The v2.49.4 regression that **motivated this entire encounter-sim
suite**. From the plan's intro: "v2.49.4 added a 💀 skull overlay
on 0-HP tokens. The skull never fired in real play. The Python
harness suite passed all 212 tests because the broadcast was
correct — but the canvas IIFE couldn't see ``window.battle``
(closure-scoped). A UI-layer test that placed Fireball + asserted
'skull is visible at (x, y) on the canvas after damage applied'
would have caught it." This is that test.

Setup:
  1. Seed Pip's combatant at ``hp_cur=0, hp_max=35`` so the canvas
     IIFE's render-loop walks ``window.battle.combatants`` and finds
     a matching combatant for Pip's existing demo token.
  2. Pre-populate the GM page's localStorage with the same battle
     state via ``seed_battle_into_page`` so the page-load IIFE picks
     up the seeded combatants (the GM ignores ``battle_update``
     broadcasts per the v2.5.5 echo-loop guard).
  3. Open the GM tabletop. The page paints; the skull render fires
     for any token whose linked combatant has ``hp_current <= 0 AND
     hp_max > 0``.
  4. ``CanvasReader.token_center_pixel`` samples the canvas at Pip's
     token center via ``ctx.getImageData(x, y, 1, 1)``.
  5. Assert the sampled pixel matches a skull-y signature
     (saturated black or saturated white — the emoji glyph or its
     stroke), not Pip's normal portrait mid-tones.

The heuristic isn't bulletproof — a portrait with a white-or-black
center pixel could fool it — but in the demo Pip's portrait has
mid-range tones, so the saturation jump from "alive portrait" to
"dead skull" is a reliable signal in practice. A stricter test
would compare alive-vs-dead pixels side-by-side; filed as a
follow-up if this heuristic flakes.
"""
from __future__ import annotations

from playwright.sync_api import BrowserContext, expect

from ...conftest import tabletop_url
from ...helpers.battle import (
    death_save_override,
    find_token_for_character,
    make_combatant,
    seed_battle,
    seed_battle_into_page,
)
from ...pages.canvas import CanvasReader
from ...pages.tabletop import TabletopPage


PIP_CID = "es_skull_pip"


def test_skull_overlay_renders_on_zero_hp_token(
    gm_context: BrowserContext,
    roster: dict,
):
    pip = roster["Pip Quickfingers"]
    # Restore Pip to alive at end-of-test even if assertions fail.
    death_save_override(pip["id"], status="alive", successes=0, failures=0)

    # Seed Pip at hp_cur=0. The combatant.char_id matches Pip's demo
    # token's character_id, so the canvas IIFE's combatant-lookup
    # finds her and draws the skull.
    combatants = [
        make_combatant(
            PIP_CID,
            char_id=pip["id"],
            name="Pip Quickfingers",
            hp_cur=0,
            hp_max=35,
            initiative=15,
        ),
    ]
    seed_battle(combatants)
    seed_battle_into_page(gm_context, combatants)

    gm_page = gm_context.new_page()
    gm_page.goto(tabletop_url())
    gm_page.evaluate("window._openDrawerPanel('players-drawer')")

    tabletop = TabletopPage(gm_page)
    expect(tabletop.combatant_row("Pip Quickfingers")).to_be_visible(timeout=5000)

    try:
        # Token coords come from ``/api/campaign/{cid}/tokens`` (the
        # page's ``allTokens`` is closure-local in the IIFE and not
        # readable via ``window``). Position lives on the active map.
        token = find_token_for_character(pip["id"])
        assert token is not None, (
            "Pip has no token on the demo map. Either the demo seed "
            "removed her or the active map changed."
        )

        canvas = CanvasReader(gm_page)
        # Wait for the canvas render loop to paint the skull AFTER the
        # seeded battle is applied. v2.49.240: replaced the fixed 500ms
        # wait with a poll-and-retry loop — CI runners are slower than
        # local machines and the original wait was racing the canvas
        # requestAnimationFrame on some runs (test went red 2026-05-25
        # CI on v2.49.236 / v2.49.239 but passed locally + on v2.49.237).
        # Polls every 250ms up to ~6s for the skull-glyph signature.
        rgba = None
        total = 0
        for _ in range(24):
            gm_page.wait_for_timeout(250)
            rgba = canvas.pixel_at_token_center(token)
            if rgba is None:
                continue
            r, g, b, _a = rgba
            total = r + g + b
            if total >= 700 or total <= 60:
                break

        assert rgba is not None, "canvas pixel sample returned None"
        r, g, b, a = rgba
        total = r + g + b
        # Skull-y signature: glyph fill (white, total ≥ 700) or
        # glyph stroke (black, total ≤ 60). A normal portrait pixel
        # lands in the mid-range; if the skull DIDN'T render, we'd
        # see Pip's portrait colors (or the canvas background).
        assert total >= 700 or total <= 60, (
            f"Token center pixel {rgba} (RGB sum {total}) looks like "
            f"a portrait or background, not a skull glyph. "
            f"Expected total ≥ 700 (skull fill) or ≤ 60 (skull stroke). "
            f"This is the v2.49.4 regression class — the broadcast set "
            f"Pip's hp_current=0 but the canvas IIFE didn't draw the "
            f"💀 overlay. Check that ``window.battle`` is populated "
            f"and that the skull-render pass at tabletop.js:777 runs "
            f"after ``drawToken``."
        )

        # Bonus assertion: the heuristic helper agrees.
        assert canvas.has_skull_overlay_at_token(token), (
            "has_skull_overlay_at_token returned False even though "
            "pixel_at_token_center matched the skull signature. The two "
            "helpers should agree — investigate."
        )
    finally:
        death_save_override(pip["id"], status="alive", successes=0, failures=0)
