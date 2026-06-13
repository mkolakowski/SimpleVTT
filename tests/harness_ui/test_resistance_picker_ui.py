"""v2.189.0 — Potion of Resistance drink-time damage-type picker UI.

The HTTP harness (`test_potion_of_resistance_drink_time_pick.py`) proves
the `/use_item_action` `resistance_type` override halves the chosen type.
This file proves the sheet UI surface: a 🧪 Drink button on the Potion of
Resistance row, a damage-type dropdown modal for the GENERIC (untyped)
potion, and that submitting the modal POSTs the chosen `resistance_type`.

Garrik Ironside carries three potion-of-resistance rows (fire, cold, and
a generic untyped one). `has_text="Potion of Resistance"` matches only the
generic row — the typed rows read "Potion of Fire/Cold Resistance".
"""
import json

from playwright.sync_api import Page, expect

from .conftest import sheet_url


def test_generic_resistance_drink_button_renders(gm_page: Page, roster: dict):
    """The generic Potion of Resistance row shows a 🧪 Drink button
    (resistance-pick kind in ITEM_ACTION_SLUGS, equipped consumable)."""
    garrik = roster["Garrik Ironside"]
    page = gm_page
    page.goto(sheet_url(garrik["id"]))

    row = page.locator(".inv-row", has_text="Potion of Resistance")
    expect(row.first).to_be_visible(timeout=5000)

    btn = row.first.locator(".inv-item-action")
    expect(btn).to_be_visible()
    expect(btn).to_contain_text("Drink")


def test_generic_potion_opens_type_picker_modal(gm_page: Page, roster: dict):
    """Clicking 🧪 Drink on the GENERIC potion opens the type-picker
    modal with a <select> of the ten RAW damage types. Cancel dismisses
    it without firing the endpoint."""
    garrik = roster["Garrik Ironside"]
    page = gm_page
    page.goto(sheet_url(garrik["id"]))

    row = page.locator(".inv-row", has_text="Potion of Resistance").first
    expect(row).to_be_visible(timeout=5000)
    row.locator(".inv-item-action").click()

    modal = page.locator("#item-action-modal")
    expect(modal).to_be_visible(timeout=2000)
    expect(modal).to_contain_text("Potion of Resistance")

    sel = modal.locator("#ia-rtype")
    expect(sel).to_be_visible()
    expect(sel.locator("option")).to_have_count(10)

    modal.locator("#ia-cancel").click()
    expect(modal).to_be_hidden()


def test_generic_potion_drink_posts_chosen_type(gm_page: Page, roster: dict):
    """Picking a damage type and clicking Drink POSTs /use_item_action
    with `action_key: "drink"` + the chosen `resistance_type`. The POST
    is intercepted so the seeded potion isn't actually consumed."""
    garrik = roster["Garrik Ironside"]
    page = gm_page

    def _handle_use(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({
                "ok": True, "item_name": "Potion of Resistance",
                "action_key": "drink", "buff_key": "resistance-radiant",
                "buff_installed": False, "consumed": True,
                "remaining_qty": 0, "temp_hp_granted": 0,
            }),
        )
    page.route("**/use_item_action", _handle_use)

    page.goto(sheet_url(garrik["id"]))
    row = page.locator(".inv-row", has_text="Potion of Resistance").first
    expect(row).to_be_visible(timeout=5000)

    with page.expect_request(
        lambda req: (
            req.url.endswith("/use_item_action") and req.method == "POST"
        ),
        timeout=10000,
    ) as req_info:
        row.locator(".inv-item-action").click()
        modal = page.locator("#item-action-modal")
        expect(modal).to_be_visible(timeout=2000)
        modal.locator("#ia-rtype").select_option("radiant")
        modal.locator("#ia-confirm").click()

    payload = req_info.value.post_data_json
    assert payload["action_key"] == "drink", payload
    assert payload["resistance_type"] == "radiant", payload
