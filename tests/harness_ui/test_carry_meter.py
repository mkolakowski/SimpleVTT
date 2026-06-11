"""v2.159.28 — carrying-capacity Phase 2a: carry meter on the sheet
inventory header.

The sheet template (`app/templates/sheet_dnd5e.html`) renders a
weight indicator like ``Weight: 78 / 270 lb`` next to the inventory
heading. The total is summed from each inventory item's `weight_lb`
field (preferred — populated by the demo seed in v2.159.28) or the
legacy `weight` string fallback. The capacity is read from the
`abilities.STR` input field via the standard `STR × 15 lb` formula.

Pip and Magnus and other PCs whose inventories haven't been backfilled
yet show ``0 / N lb`` until their seeds get the `weight_lb` data
(Phase 2b — filed).

Tests:
  - Krieger's sheet shows the meter with both a numeric weight + a
    numeric capacity (no dashes). His STR 18 → cap 270.
  - The total weight number is positive (because v2.159.28 backfilled
    his items).
"""
from playwright.sync_api import Page, expect

from .conftest import sheet_url


def test_krieger_carry_meter_renders(gm_page: Page, roster: dict):
    """v2.159.28: navigate to Krieger's sheet → carry meter shows
    `Weight: <n> / 270 lb` with non-zero <n>."""
    krieger = roster["Krieger Stonefist"]
    page = gm_page
    page.goto(sheet_url(krieger["id"]))

    weight_span = page.locator("#inv-total-weight")
    cap_span = page.locator("#inv-carry-capacity")
    expect(weight_span).to_be_visible(timeout=5000)
    expect(cap_span).to_be_visible(timeout=5000)

    cap_text = cap_span.text_content() or ""
    # Krieger's STR 18 → cap 270.
    assert cap_text == "270", (
        f"expected capacity 270; got {cap_text!r}"
    )

    weight_text = (weight_span.text_content() or "").strip()
    # v2.159.28: Krieger's backfilled inventory should sum to
    # ≥ 70 lb. Greataxe (7) + 4 Javelins (8) + Explorer's pack (59)
    # + Staff (1) + 2 Potions (1) + Javelin of Lightning (2) = 78 lb.
    try:
        weight_n = float(weight_text)
    except ValueError:
        weight_n = 0
    assert weight_n >= 70, (
        f"expected weight ≥ 70 lb; got {weight_text!r} ({weight_n})"
    )
    assert weight_n < 270, (
        f"weight ({weight_n}) should be under cap (270); test data may have drifted"
    )
