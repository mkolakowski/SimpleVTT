"""v2.167.0 — legendary-resistance Phase 2 UI on the GM initiative tracker.

The HTTP harness `tests/harness/test_spend_legendary_resistance.py` +
`tests/harness/test_legendary_resistance_prompt.py` cover the endpoint
contracts (the per-day pool, the spend/decline flip, the deferred-save
broadcasts). This file covers the browser-side surface v2.167.0 adds to
`tabletop.html`:

  - A legendary creature's init-tracker card renders the 🛡️ charge
    badge (`.legendary-lr-meter`, ◆/◇ diamonds, current/max) when the
    combatant carries a `legendary_resistance` pool — independent of
    whether it also has legendary-action options.
  - A `legendary_resistance_prompt` WS message surfaces the floating
    GM banner (`#_legendary_resistance_prompt`) with a Spend / Decline
    button pair per pending prompt.
  - Clicking Spend POSTs `/spend_legendary_resistance` carrying the
    prompt_id; the following `legendary_resistance_resolved` broadcast
    clears the banner row.

Seeding mirrors `test_legendary_action_buttons.py`: the battle is
pre-baked into `localStorage` before load. The dragon is a "manual"
entry (no char_id / token_template_id) carrying its
`legendary_resistance` pool directly, so the render reads it without a
legendary monster template in the demo campaign.
"""
import json

from playwright.sync_api import Page, expect

from .conftest import CAMPAIGN_ID, tabletop_url


_DRAGON_ID = "npc_dragon_lr_ui_test"
_HERO_ID = "tok_hero_lr_ui_test"
_PROMPT_ID = "lrpromptui01"


def _battle_json() -> str:
    """A Hero (active) + an Ancient Red Dragon carrying a pre-baked
    legendary-resistance pool (3/3). The Hero is active (turn_index=0)."""
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
                "legendary_resistance": {"max": 3, "current": 3},
            },
        ],
        "turn_index": 0,
        "round": 1,
        "active": True,
    })


def _seed_battle(page: Page) -> None:
    page.add_init_script(
        f"window.localStorage.setItem('simplevtt_battle_{CAMPAIGN_ID}', "
        f"{json.dumps(_battle_json())});"
    )


def _dispatch_prompt(page: Page, current: int = 3) -> None:
    page.evaluate(
        """(args) => {
            document.dispatchEvent(new CustomEvent('vtt:ws-message', {detail: {
                type: 'legendary_resistance_prompt',
                data: {
                    prompt_id: args.promptId,
                    combatant_id: args.dragonId,
                    combatant_name: 'Ancient Red Dragon',
                    save_ability: 'wis',
                    save_dc: 16,
                    feature_name: 'Menacing Attack',
                    condition_key: 'frightened',
                    current: args.current,
                    max: 3,
                },
            }}));
        }""",
        {"promptId": _PROMPT_ID, "dragonId": _DRAGON_ID, "current": current},
    )


def test_lr_badge_renders(gm_page: Page):
    """The dragon's card shows the 🛡️ legendary-resistance badge with
    the seeded 3/3 count, even though it has no legendary-action options."""
    _seed_battle(gm_page)
    gm_page.goto(tabletop_url())

    dragon_entry = gm_page.locator(f'.init-entry[data-char-id="{_DRAGON_ID}"]')
    expect(dragon_entry).to_be_visible(timeout=5000)

    badge = dragon_entry.locator(".legendary-lr-meter")
    expect(badge).to_be_visible()
    expect(badge).to_contain_text("3/3")
    # No action-option buttons seeded → only the LR badge, no 👑 meter.
    expect(dragon_entry.locator(".legendary-meter")).to_have_count(0)


def test_lr_prompt_banner_appears_and_spend_clears_it(gm_page: Page):
    """A legendary_resistance_prompt WS message surfaces the floating
    Spend/Decline banner; clicking Spend POSTs /spend_legendary_resistance
    with the prompt_id, and the following resolved broadcast clears it."""
    _seed_battle(gm_page)

    captured = {}

    def _handle(route):
        try:
            captured.update(route.request.post_data_json or {})
        except Exception:
            pass
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({
                "ok": True,
                "combatant_id": _DRAGON_ID,
                "combatant_name": "Ancient Red Dragon",
                "max": 3, "current": 2,
                "prompt_id": _PROMPT_ID,
                "resolution": "spent",
            }),
        )

    gm_page.route("**/spend_legendary_resistance", _handle)
    gm_page.goto(tabletop_url())

    dragon_entry = gm_page.locator(f'.init-entry[data-char-id="{_DRAGON_ID}"]')
    expect(dragon_entry).to_be_visible(timeout=5000)

    # No prompt yet → banner absent.
    expect(gm_page.locator("#_legendary_resistance_prompt")).to_have_count(0)

    _dispatch_prompt(gm_page, current=3)

    banner = gm_page.locator("#_legendary_resistance_prompt")
    expect(banner).to_be_visible(timeout=3000)
    expect(banner).to_contain_text("Ancient Red Dragon")
    expect(banner).to_contain_text("WIS DC 16")
    spend_btn = banner.locator("._lr_spend_btn")
    expect(spend_btn).to_contain_text("Spend (3 left)")
    expect(banner.locator("._lr_decline_btn")).to_contain_text("Decline")

    with gm_page.expect_request("**/spend_legendary_resistance") as req_info:
        spend_btn.click()
    req_info.value
    assert captured.get("prompt_id") == _PROMPT_ID, captured

    # The server answers with legendary_resistance_resolved → banner clears.
    gm_page.evaluate(
        """(promptId) => {
            document.dispatchEvent(new CustomEvent('vtt:ws-message', {detail: {
                type: 'legendary_resistance_resolved',
                data: {prompt_id: promptId, combatant_id: '%s', passed: true,
                       condition_installed: false, condition_key: '', reason: 'spent',
                       max: 3, current: 2},
            }}));
        }""" % _DRAGON_ID,
        _PROMPT_ID,
    )
    expect(gm_page.locator("#_legendary_resistance_prompt")).to_have_count(0, timeout=3000)


def test_lr_decline_button_posts_decline(gm_page: Page):
    """Clicking Decline POSTs /decline_legendary_resistance with the
    prompt_id (the held condition installs server-side)."""
    _seed_battle(gm_page)

    captured = {}

    def _handle(route):
        try:
            captured.update(route.request.post_data_json or {})
        except Exception:
            pass
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({
                "ok": True,
                "prompt_id": _PROMPT_ID,
                "combatant_id": _DRAGON_ID,
                "combatant_name": "Ancient Red Dragon",
                "condition_installed": True,
                "condition_key": "frightened",
                "resolution": "declined",
            }),
        )

    gm_page.route("**/decline_legendary_resistance", _handle)
    gm_page.goto(tabletop_url())

    dragon_entry = gm_page.locator(f'.init-entry[data-char-id="{_DRAGON_ID}"]')
    expect(dragon_entry).to_be_visible(timeout=5000)
    _dispatch_prompt(gm_page, current=3)

    banner = gm_page.locator("#_legendary_resistance_prompt")
    expect(banner).to_be_visible(timeout=3000)

    with gm_page.expect_request("**/decline_legendary_resistance") as req_info:
        banner.locator("._lr_decline_btn").click()
    req_info.value
    assert captured.get("prompt_id") == _PROMPT_ID, captured
