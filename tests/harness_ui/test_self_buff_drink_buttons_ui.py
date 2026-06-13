"""v2.191.0 — plain Drink buttons for the parameterless self-buff
potions. Potion of Heroism (v2.184.0), Potion of Speed (v2.185.0), and
Potion of Invulnerability (v2.190.0) were API-only — only Potion of
Resistance got a sheet button (v2.189.0). This file proves the three
`self-buff-drink` rows now render a Drink button and that clicking one
POSTs `/use_item_action` with `action_key: "drink"` and no extra params
(no modal — these potions take no parameter).

Garrik Ironside carries all three potions. Each name is unique, so a
`has_text=` locator matches exactly one inventory row.
"""
import json

from playwright.sync_api import Page, expect

from .conftest import sheet_url


def test_self_buff_drink_buttons_render(gm_page: Page, roster: dict):
    """All three parameterless self-buff potion rows show a Drink
    button (self-buff-drink kind in ITEM_ACTION_SLUGS, equipped
    consumable)."""
    garrik = roster["Garrik Ironside"]
    page = gm_page
    page.goto(sheet_url(garrik["id"]))

    for name in ("Potion of Heroism", "Potion of Speed",
                 "Potion of Invulnerability"):
        row = page.locator(".inv-row", has_text=name).first
        expect(row).to_be_visible(timeout=5000)
        btn = row.locator(".inv-item-action")
        expect(btn).to_be_visible()
        expect(btn).to_contain_text("Drink")


def test_invulnerability_drink_posts_plain_action(
    gm_page: Page, roster: dict,
):
    """Clicking 🛡️ Drink on Potion of Invulnerability POSTs
    /use_item_action with `action_key: "drink"` and NO modal / no
    resistance_type. The POST is intercepted so the seeded potion isn't
    consumed."""
    garrik = roster["Garrik Ironside"]
    page = gm_page

    def _handle_use(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({
                "ok": True, "item_name": "Potion of Invulnerability",
                "action_key": "drink", "buff_key": "resistance-all",
                "buff_installed": False, "consumed": True,
                "remaining_qty": 0, "temp_hp_granted": 0,
            }),
        )
    page.route("**/use_item_action", _handle_use)

    page.goto(sheet_url(garrik["id"]))
    row = page.locator(
        ".inv-row", has_text="Potion of Invulnerability",
    ).first
    expect(row).to_be_visible(timeout=5000)

    with page.expect_request(
        lambda req: (
            req.url.endswith("/use_item_action") and req.method == "POST"
        ),
        timeout=10000,
    ) as req_info:
        row.locator(".inv-item-action").click()

    payload = req_info.value.post_data_json
    assert payload["action_key"] == "drink", payload
    assert "resistance_type" not in payload, payload
