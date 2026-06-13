"""v2.214.0 — ability-score override Phase 2a: boosted ability score on
the sheet card.

The ability card (`app/templates/sheet_dnd5e.html` `#ab-card-view`) renders
the EFFECTIVE score + modifier with an item-boosted marker (a ▲ badge +
accent colour) when an equipped item sets the score above its base (RAW
max(base, set) — Belt of Giant Strength, DMG p.155). See
docs/plans/str-override.md.

Demo fixture: Garrik Ironside (Fighter, base STR 18 → mod +4) wears an
equipped+attuned Belt of Giant Strength (Hill, STR 21 → mod +5). So his STR
card shows 21 with the boost badge visible, while DEX (14, no override)
shows the base value with the badge hidden.
"""
from playwright.sync_api import Page, expect

from .conftest import sheet_url


def test_garrik_str_card_shows_boosted_score(gm_page: Page, roster: dict):
    """Garrik's STR ability card renders the effective 21 (not the base 18),
    a +5 modifier, and a visible item-boost badge."""
    garrik = roster["Garrik Ironside"]
    page = gm_page
    page.goto(sheet_url(garrik["id"]))

    str_score = page.locator('.ab-score-disp[data-ab="STR"]')
    expect(str_score).to_be_visible(timeout=5000)
    assert (str_score.text_content() or "").strip() == "21", (
        f"expected effective STR 21; got {str_score.text_content()!r}"
    )

    str_mod = page.locator('.ab-mod-disp[data-ab="STR"]')
    assert (str_mod.text_content() or "").strip() == "+5", (
        f"expected STR modifier +5; got {str_mod.text_content()!r}"
    )

    str_badge = page.locator('.ab-boost-badge[data-ab="STR"]')
    expect(str_badge).to_be_visible(timeout=5000)


def test_garrik_dex_card_unboosted(gm_page: Page, roster: dict):
    """DEX has no override → the card shows the base 14 and the boost badge
    is hidden."""
    garrik = roster["Garrik Ironside"]
    page = gm_page
    page.goto(sheet_url(garrik["id"]))

    dex_score = page.locator('.ab-score-disp[data-ab="DEX"]')
    expect(dex_score).to_be_visible(timeout=5000)
    assert (dex_score.text_content() or "").strip() == "14", (
        f"expected base DEX 14; got {dex_score.text_content()!r}"
    )

    dex_badge = page.locator('.ab-boost-badge[data-ab="DEX"]')
    expect(dex_badge).to_be_hidden()
