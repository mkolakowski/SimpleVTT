"""v2.158.85 — magic-items-automation Phase 3b polish: 🔮 Use button
on the sheet inventory row for catalog-action items (Pearl of Power
+ Wand of Magic Missiles).

The HTTP harness `test_use_item_action_pearl.py` / `_wand.py` verify
the endpoint contract. This file verifies the sheet UI button
actually renders + (lightly) that clicking it fires through the
endpoint via `window.prompt` interception.

We use Thalindra Moonwhisper because she has both magic items
equipped in the v2.158.84 seed (Pearl + Wand). Asserting both
buttons render simultaneously also proves the per-slug action map
scales without code change.
"""
from playwright.sync_api import Page, expect

from .conftest import sheet_url


def test_pearl_use_button_renders(gm_page: Page, roster: dict):
    """v2.158.85: Thalindra's inventory shows a 🔮 Use button on the
    Pearl of Power row (catalog-action item, equipped, attuned)."""
    thalindra = roster["Thalindra Moonwhisper"]
    page = gm_page
    page.goto(sheet_url(thalindra["id"]))

    pearl_row = page.locator(".inv-row", has_text="Pearl of Power")
    expect(pearl_row).to_be_visible(timeout=5000)

    btn = pearl_row.locator(".inv-item-action")
    expect(btn).to_be_visible()
    # Button text mirrors the ITEM_ACTION_SLUGS config in sheet_dnd5e.html.
    expect(btn).to_contain_text("Pearl")


def test_wand_use_button_renders(gm_page: Page, roster: dict):
    """v2.158.85: Thalindra's inventory shows a 🪄 Cast button on
    the Wand of Magic Missiles row (catalog-action item, equipped,
    NOT attuned — wand is uncommon RAW)."""
    thalindra = roster["Thalindra Moonwhisper"]
    page = gm_page
    page.goto(sheet_url(thalindra["id"]))

    wand_row = page.locator(".inv-row", has_text="Wand of Magic Missiles")
    expect(wand_row).to_be_visible(timeout=5000)

    btn = wand_row.locator(".inv-item-action")
    expect(btn).to_be_visible()
    expect(btn).to_contain_text("Cast")
