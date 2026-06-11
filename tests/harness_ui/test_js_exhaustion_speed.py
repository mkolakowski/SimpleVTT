"""v2.159.22 — JS-side exhaustion speed wiring (closes v2.159.19 filed
follow-up).

The server-side `effective_speed_walk` in `app/content/effective_speed.py`
has been honoring exhaustion since v2.159.19 (Lv 2 halves, Lv 5 floors
to 0). The browser-side mirror `_effectiveSpeedWalk` in `tabletop.html`
didn't — so a Lv 2 PC's move-preview ring on the canvas showed the
unhalved cap, then the server rejected the move with 409
over_speed_cap. The UX was informative-then-rejecting.

This commit ports the v2.159.19 server formula to the JS mirror. The
tests below drive the function directly via `page.evaluate` on the
tabletop page (the campaign URL).
"""
from playwright.sync_api import Page, expect

from .conftest import tabletop_url


def test_js_effective_speed_walk_lv0_unchanged(gm_page: Page):
    """v2.159.22 baseline. Lv 0 → 30 (regression guard)."""
    gm_page.goto(tabletop_url())
    result = gm_page.evaluate("""
        () => window._effectiveSpeedWalk({
            speed_walk: 30, buffs: [], exhaustion_level: 0,
        })
    """)
    assert result == 30


def test_js_effective_speed_walk_lv2_halves(gm_page: Page):
    """v2.159.22: Lv 2 → 30 // 2 = 15."""
    gm_page.goto(tabletop_url())
    result = gm_page.evaluate("""
        () => window._effectiveSpeedWalk({
            speed_walk: 30, buffs: [], exhaustion_level: 2,
        })
    """)
    assert result == 15


def test_js_effective_speed_walk_lv5_floors_to_zero(gm_page: Page):
    """v2.159.22: Lv 5 → 0 (hard floor)."""
    gm_page.goto(tabletop_url())
    result = gm_page.evaluate("""
        () => window._effectiveSpeedWalk({
            speed_walk: 30, buffs: [], exhaustion_level: 5,
        })
    """)
    assert result == 0


def test_js_effective_speed_walk_lv5_with_haste_still_zero(
    gm_page: Page,
):
    """v2.159.22: Lv 5 hard floor — even Haste's ×2 multiplier can't
    restore speed."""
    gm_page.goto(tabletop_url())
    result = gm_page.evaluate("""
        () => window._effectiveSpeedWalk({
            speed_walk: 30,
            buffs: [{key: 'haste', effects: {speed_multiplier: 2}}],
            exhaustion_level: 5,
        })
    """)
    assert result == 0


def test_js_effective_speed_walk_lv2_composes_with_slow(
    gm_page: Page,
):
    """v2.159.22: Lv 2 + Slow (-10 ft) → (30 - 10) // 2 = 10."""
    gm_page.goto(tabletop_url())
    result = gm_page.evaluate("""
        () => window._effectiveSpeedWalk({
            speed_walk: 30,
            buffs: [{key: 'slow', effects: {speed_reduction_ft: 10}}],
            exhaustion_level: 2,
        })
    """)
    assert result == 10
