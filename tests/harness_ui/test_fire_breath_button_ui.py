"""v2.194.0 — the Potion of Fire Breath sheet button. The offensive
consumable shipped API-only in v2.193.0; this adds the `aoe-sphere`
ITEM_ACTION_SLUGS entry so the inventory row renders an 🔥 Exhale Fire
button (the full center-target → sphere-targets → AoE-confirm click chain
needs a loaded battle/map, so this proves the button renders only).

Garrik Ironside carries the seeded Potion of Fire Breath.
"""
from playwright.sync_api import Page, expect

from .conftest import sheet_url


def test_fire_breath_button_renders(gm_page: Page, roster: dict):
    """Garrik's Potion of Fire Breath row shows an 🔥 Exhale Fire button
    (aoe-sphere kind in ITEM_ACTION_SLUGS, equipped consumable)."""
    garrik = roster["Garrik Ironside"]
    page = gm_page
    page.goto(sheet_url(garrik["id"]))

    row = page.locator(".inv-row", has_text="Potion of Fire Breath").first
    expect(row).to_be_visible(timeout=5000)
    btn = row.locator(".inv-item-action")
    expect(btn).to_be_visible()
    expect(btn).to_contain_text("Exhale Fire")
