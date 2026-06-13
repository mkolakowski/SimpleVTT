"""v2.198.0 — the Potion of Mind Reading sheet button. The save-imposing
consumable shipped API-only in v2.197.0; this adds the `single-target-save`
ITEM_ACTION_SLUGS entry so the inventory row renders a 🧠 Read Thoughts
button (the full picker → POST click chain needs a loaded battle/map, so
this proves the button renders only).

Garrik Ironside carries the seeded Potion of Mind Reading.
"""
from playwright.sync_api import Page, expect

from .conftest import sheet_url


def test_mind_reading_button_renders(gm_page: Page, roster: dict):
    """Garrik's Potion of Mind Reading row shows a 🧠 Read Thoughts button
    (single-target-save kind in ITEM_ACTION_SLUGS, equipped consumable)."""
    garrik = roster["Garrik Ironside"]
    page = gm_page
    page.goto(sheet_url(garrik["id"]))

    row = page.locator(".inv-row", has_text="Potion of Mind Reading").first
    expect(row).to_be_visible(timeout=5000)
    btn = row.locator(".inv-item-action")
    expect(btn).to_be_visible()
    expect(btn).to_contain_text("Read Thoughts")
