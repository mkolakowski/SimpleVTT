"""v2.160.0 — legendary-action UI strip on the GM initiative tracker.

The HTTP harness `tests/harness/test_use_legendary_action.py` covers
the `/use_legendary_action` endpoint contract (budget gate, own-turn
409, pool decrement, broadcasts). This file covers the browser-side
surface the v2.160.0 commit adds to `tabletop.html`:

  - A legendary creature's init-tracker card renders a `.legendary-strip`
    with a pool meter (👑 ●●● 3/3) + one `.legendary-act-btn` per
    option, each carrying its cost in a `.la-cost` pill.
  - Buttons disable on the creature's OWN turn (RAW DMG p.11:
    legendary actions are spent at the END of another creature's turn).
  - Clicking an enabled button POSTs to `/use_legendary_action` with
    the combatant id + action id/name + cost.

Seeding: we pre-bake the battle into `localStorage` before the page
loads (the GM init tracker hydrates from `simplevtt_battle_<cid>`).
Both combatants are "manual" entries (no char_id / token_template_id)
so the v2.25.1 orphan-cleanup keeps them. The dragon carries
`legendary_action_options` directly, so the render reads them without
needing a legendary monster template in the demo campaign.
"""
import json

from playwright.sync_api import Page, expect

from .conftest import CAMPAIGN_ID, tabletop_url


_DRAGON_ID = "npc_dragon_ui_test"
_HERO_ID = "tok_hero_ui_test"


def _battle_json(turn_index: int) -> str:
    """Two manual combatants: a Hero (active when turn_index=0) and an
    Ancient Red Dragon carrying a pre-baked legendary-action pool +
    options. turn_index selects who is active."""
    return json.dumps({
        "combatants": [
            {
                "id": _HERO_ID,
                "char_id": None,
                "token_template_id": None,
                "name": "Hero of the Hour",
                "initiative": 25,
                "hp_current": 30, "hp_max": 30,
                "buffs": [],
                "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
            },
            {
                "id": _DRAGON_ID,
                "char_id": None,
                "token_template_id": None,
                "name": "Ancient Red Dragon",
                "initiative": 20,
                "hp_current": 546, "hp_max": 546,
                "buffs": [],
                "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
                "legendary_actions": {"max": 3, "current": 3},
                "legendary_action_options": [
                    {"id": "tail-attack", "name": "Tail Attack", "cost": 1},
                    {"id": "wing-attack-costs-2-actions", "name": "Wing Attack", "cost": 2},
                ],
            },
        ],
        "turn_index": turn_index,
        "round": 1,
        "active": True,
    })


def _seed_battle(page: Page, turn_index: int) -> None:
    page.add_init_script(
        f"window.localStorage.setItem('simplevtt_battle_{CAMPAIGN_ID}', "
        f"{json.dumps(_battle_json(turn_index))});"
    )


def test_legendary_strip_renders_meter_and_buttons(gm_page: Page):
    """Dragon card shows the pool meter (3/3) + a button per option,
    each with its cost pill. Hero is active (turn_index=0) so the
    dragon's buttons are enabled."""
    _seed_battle(gm_page, turn_index=0)
    gm_page.goto(tabletop_url())

    dragon_entry = gm_page.locator(f'.init-entry[data-char-id="{_DRAGON_ID}"]')
    expect(dragon_entry).to_be_visible(timeout=5000)

    strip = dragon_entry.locator(".legendary-strip")
    expect(strip).to_be_visible()
    expect(strip.locator(".legendary-meter")).to_contain_text("3/3")

    btns = dragon_entry.locator(".legendary-act-btn")
    expect(btns).to_have_count(2)
    expect(btns.nth(0)).to_contain_text("Tail Attack")
    expect(btns.nth(1)).to_contain_text("Wing Attack")
    # Cost pills: 1 for Tail, 2 for Wing.
    expect(btns.nth(0).locator(".la-cost")).to_have_text("1")
    expect(btns.nth(1).locator(".la-cost")).to_have_text("2")
    # Hero active → dragon NOT on its own turn → buttons enabled.
    expect(btns.nth(0)).to_be_enabled()
    expect(btns.nth(1)).to_be_enabled()


def test_legendary_buttons_disabled_on_own_turn(gm_page: Page):
    """turn_index=1 → the dragon is the active combatant → both spend
    buttons are disabled (RAW: never on the creature's own turn)."""
    _seed_battle(gm_page, turn_index=1)
    gm_page.goto(tabletop_url())

    dragon_entry = gm_page.locator(f'.init-entry[data-char-id="{_DRAGON_ID}"]')
    expect(dragon_entry).to_be_visible(timeout=5000)

    btns = dragon_entry.locator(".legendary-act-btn")
    expect(btns).to_have_count(2)
    expect(btns.nth(0)).to_be_disabled()
    expect(btns.nth(1)).to_be_disabled()


def test_legendary_button_click_posts_use_legendary_action(gm_page: Page):
    """Clicking the enabled Wing Attack button issues a POST to
    /use_legendary_action carrying the combatant id, action id/name,
    and cost 2. We intercept + fulfill the request so the assertion
    doesn't depend on the server's hub holding this seeded battle."""
    _seed_battle(gm_page, turn_index=0)

    captured = {}

    def _handle(route):
        req = route.request
        try:
            captured.update(req.post_data_json or {})
        except Exception:
            pass
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"ok": True, "pool_current": 1, "pool_max": 3}),
        )

    gm_page.route("**/use_legendary_action", _handle)
    gm_page.goto(tabletop_url())

    dragon_entry = gm_page.locator(f'.init-entry[data-char-id="{_DRAGON_ID}"]')
    expect(dragon_entry).to_be_visible(timeout=5000)
    wing_btn = dragon_entry.locator(".legendary-act-btn", has_text="Wing Attack")
    expect(wing_btn).to_be_enabled()

    with gm_page.expect_request("**/use_legendary_action") as req_info:
        wing_btn.click()
    req_info.value  # ensure the request actually fired

    assert captured.get("combatant_id") == _DRAGON_ID, captured
    assert captured.get("action_id") == "wing-attack-costs-2-actions", captured
    assert captured.get("action_name") == "Wing Attack", captured
    assert captured.get("cost") == 2, captured
