"""Champion Fighter Lv 7+ Remarkable Athlete client-side check.

v2.49.237 — RAW (PHB p.72): "Starting at 7th level, you can add half
your proficiency bonus (round up) to any Strength, Dexterity, or
Constitution check you make that doesn't already use your proficiency
bonus." The bonus lives in `sheet.js`'s ability-check + non-proficient-
skill-check paths (mirrors Bard's Jack of All Trades from v2.15.2,
which uses floor(PB/2) instead of ceiling).

Tests intercept the POST /roll request that fires on clicking an
ability check button and verify the dice expression carries the
expected ceil(PB/2) bonus on STR/DEX/CON for Garrik (Lv 7 Champion
Fighter, PB +3 → bonus +2), and that Pip (Lv 5 Rogue) gets NO bonus.

The bonus must NOT fire on:
  - INT / WIS / CHA ability checks (RAW STR/DEX/CON only)
  - Saves (always use prof, RAW excludes them)
  - Proficient skill checks (already use prof)
"""
import re

from playwright.sync_api import Page, expect

from .conftest import sheet_url


def _capture_roll_expression(page: Page, click_locator) -> str:
    """Click the locator + return the `expression` field from the
    intercepted /roll POST. The page never gets a WS connection on
    the standalone sheet, so the request is the load-bearing assertion
    surface."""
    captured: list[str] = []

    def _handler(route, request):
        # Body is JSON: {expression, visibility, note, character_id?}
        try:
            payload = request.post_data_json or {}
            captured.append(payload.get("expression", ""))
        except Exception:
            pass
        # Fulfill with a dummy 200 so the click handler doesn't error;
        # the actual roll value doesn't matter — we only care about
        # what was SENT.
        route.fulfill(
            status=200,
            content_type="application/json",
            body='{"ok": true, "total": 10, "breakdown": "1d20=10", "expression": "1d20"}',
        )

    page.route("**/api/campaign/*/roll", _handler)
    click_locator.click()
    page.wait_for_timeout(500)
    page.unroute("**/api/campaign/*/roll")
    return captured[0] if captured else ""


def _bonus_from_expression(expr: str) -> int:
    """Parse 1d20+N / 1d20-N into the signed bonus. Returns 0 for
    bare 1d20."""
    m = re.match(r"1d20([+-]?\d+)?", expr)
    if not m or not m.group(1):
        return 0
    return int(m.group(1))


def test_garrik_str_check_includes_remarkable_athlete_bonus(gm_page: Page, roster: dict):
    """Garrik (Lv 7 Champion Fighter, STR 18 → mod +4, PB +3 →
    Rmk Ath +2). Expected ability-check expression: 1d20+6.
    """
    garrik = roster["Garrik Ironside"]
    gm_page.goto(sheet_url(garrik["id"]))
    expect(gm_page.locator("[data-roll-ability='STR']").first).to_be_visible(timeout=3000)
    expr = _capture_roll_expression(
        gm_page, gm_page.locator("[data-roll-ability='STR']").first
    )
    assert _bonus_from_expression(expr) == 6, (
        f"Expected 1d20+6 for STR check (mod +4 + Rmk Ath +2); got {expr!r}"
    )


def test_garrik_dex_check_includes_remarkable_athlete_bonus(gm_page: Page, roster: dict):
    """Garrik DEX 14 → mod +2; Rmk Ath +2 → 1d20+4."""
    garrik = roster["Garrik Ironside"]
    gm_page.goto(sheet_url(garrik["id"]))
    expect(gm_page.locator("[data-roll-ability='DEX']").first).to_be_visible(timeout=3000)
    expr = _capture_roll_expression(
        gm_page, gm_page.locator("[data-roll-ability='DEX']").first
    )
    assert _bonus_from_expression(expr) == 4, (
        f"Expected 1d20+4 for DEX check (mod +2 + Rmk Ath +2); got {expr!r}"
    )


def test_garrik_int_check_excludes_remarkable_athlete_bonus(gm_page: Page, roster: dict):
    """Garrik INT 8 → mod -1; Remarkable Athlete is STR/DEX/CON only,
    so INT check should be a bare 1d20-1 with NO bonus."""
    garrik = roster["Garrik Ironside"]
    gm_page.goto(sheet_url(garrik["id"]))
    expect(gm_page.locator("[data-roll-ability='INT']").first).to_be_visible(timeout=3000)
    expr = _capture_roll_expression(
        gm_page, gm_page.locator("[data-roll-ability='INT']").first
    )
    assert _bonus_from_expression(expr) == -1, (
        f"Expected 1d20-1 for INT check (mod -1, no Rmk Ath on INT); got {expr!r}"
    )


def test_pip_str_check_excludes_remarkable_athlete_bonus(gm_page: Page, roster: dict):
    """Pip (Rogue, not Champion Fighter) — control case. Pip has
    STR 8 (mod -1); Remarkable Athlete should NOT fire because the
    class+subclass+level gate fails. Expression must be 1d20-1.
    """
    pip = roster["Pip Quickfingers"]
    gm_page.goto(sheet_url(pip["id"]))
    expect(gm_page.locator("[data-roll-ability='STR']").first).to_be_visible(timeout=3000)
    expr = _capture_roll_expression(
        gm_page, gm_page.locator("[data-roll-ability='STR']").first
    )
    assert _bonus_from_expression(expr) == -1, (
        f"Expected 1d20-1 for Pip STR check (no Remarkable Athlete); got {expr!r}"
    )
