"""v2.170.0 — lair-action Phase 3c UI on the GM tabletop.

The HTTP harness `tests/harness/test_trigger_lair_action.py` covers the
endpoint contracts (`/set_in_lair`, `/trigger_lair_action`, the AoE
save dispatch, the carry-forward guard). This file covers the
browser-side surface v2.170.0 adds to `tabletop.html`:

  - When the active battle holds a combatant carrying a non-empty
    `lair_actions` list, the GM sees the floating 🌋 lair-action panel
    (`#_lair_action_panel`) with an Enter/Exit toggle.
  - Toggling POSTs `/set_in_lair` carrying `{in_lair, lair_slug}`.
  - An `in_lair_changed` WS message flips the panel into the in-lair
    state, listing each action with a Trigger button.
  - Clicking Trigger opens the multi-target picker, then POSTs
    `/trigger_lair_action` with `{action_id, lair_slug,
    aoe_target_combatant_ids}`.

Seeding mirrors `test_legendary_resistance_ui.py`: the battle is
pre-baked into `localStorage`. The dragon is a "manual" entry (no
char_id / token_template_id) carrying its `lair_actions` + `lair_slug`
directly, so the render reads them without a lair-bearing monster
template in the demo campaign.
"""
import json

from playwright.sync_api import Page, expect

from .conftest import CAMPAIGN_ID, tabletop_url


_DRAGON_ID = "npc_dragon_lair_ui_test"
_HERO_ID = "tok_hero_lair_ui_test"
_LAIR_SLUG = "ancient-red-dragon"


def _battle_json(in_lair: bool = False) -> str:
    """A Hero (active) + an Ancient Red Dragon carrying two pre-baked
    lair actions and a lair_slug. The Hero is active (turn_index=0)."""
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
                "lair_slug": _LAIR_SLUG,
                "lair_actions": [
                    {
                        "id": "magma-erupts",
                        "name": "Magma Erupts",
                        "save_ability": "dex",
                        "save_dc": 15,
                        "damage": "6d6",
                        "damage_type": "fire",
                        "half_on_save": True,
                    },
                    {
                        "id": "tremor",
                        "name": "Tremor",
                        "save_ability": "dex",
                        "save_dc": 15,
                        "effect": "prone",
                    },
                ],
            },
        ],
        "turn_index": 0,
        "round": 1,
        "active": True,
        "in_lair": in_lair,
        "lair_slug": _LAIR_SLUG if in_lair else "",
    })


def _seed_battle(page: Page, in_lair: bool = False) -> None:
    page.add_init_script(
        f"window.localStorage.setItem('simplevtt_battle_{CAMPAIGN_ID}', "
        f"{json.dumps(_battle_json(in_lair))});"
    )


def _dispatch_in_lair_changed(page: Page, in_lair: bool) -> None:
    page.evaluate(
        """(args) => {
            document.dispatchEvent(new CustomEvent('vtt:ws-message', {detail: {
                type: 'in_lair_changed',
                data: {in_lair: args.inLair, lair_slug: args.slug},
            }}));
        }""",
        {"inLair": in_lair, "slug": _LAIR_SLUG},
    )


def _dispatch_lair_action_resolved(page: Page, action_id: str) -> None:
    page.evaluate(
        """(args) => {
            document.dispatchEvent(new CustomEvent('vtt:ws-message', {detail: {
                type: 'lair_action_resolved',
                data: {
                    action_id: args.actionId,
                    action_name: 'Magma Erupts',
                    last_lair_action_id: args.actionId,
                    results: [],
                },
            }}));
        }""",
        {"actionId": action_id},
    )


def test_lair_panel_toggle_renders(gm_page: Page):
    """When the battle holds a lair-bearing creature, the GM sees the
    floating lair-action panel with an "Enter lair" toggle and no action
    list (battle starts out of lair)."""
    _seed_battle(gm_page, in_lair=False)
    gm_page.goto(tabletop_url())

    dragon_entry = gm_page.locator(f'.init-entry[data-char-id="{_DRAGON_ID}"]')
    expect(dragon_entry).to_be_visible(timeout=5000)

    panel = gm_page.locator("#_lair_action_panel")
    expect(panel).to_be_visible(timeout=3000)
    expect(panel).to_contain_text("Lair Actions")
    expect(panel).to_contain_text("Ancient Red Dragon")
    toggle = panel.locator("#_lair_toggle_btn")
    expect(toggle).to_contain_text("Enter lair")
    # Out of lair → no action Trigger buttons yet.
    expect(panel.locator("._lair_trigger_btn")).to_have_count(0)


def test_in_lair_changed_shows_action_list(gm_page: Page):
    """An in_lair_changed WS message flips the panel into the in-lair
    state, listing each lair action with a Trigger button and an
    "Exit lair" toggle."""
    _seed_battle(gm_page, in_lair=False)
    gm_page.goto(tabletop_url())

    panel = gm_page.locator("#_lair_action_panel")
    expect(panel).to_be_visible(timeout=5000)
    expect(panel.locator("#_lair_toggle_btn")).to_contain_text("Enter lair")

    _dispatch_in_lair_changed(gm_page, in_lair=True)

    expect(panel.locator("#_lair_toggle_btn")).to_contain_text("Exit lair", timeout=3000)
    triggers = panel.locator("._lair_trigger_btn")
    expect(triggers).to_have_count(2)
    expect(panel).to_contain_text("Magma Erupts")
    expect(panel).to_contain_text("Tremor")
    expect(panel).to_contain_text("DEX DC 15")


def test_toggle_posts_set_in_lair(gm_page: Page):
    """Clicking the toggle POSTs /set_in_lair with the inverted in_lair
    flag and the creature's lair_slug."""
    _seed_battle(gm_page, in_lair=False)

    captured = {}

    def _handle(route):
        try:
            captured.update(route.request.post_data_json or {})
        except Exception:
            pass
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"ok": True, "in_lair": True, "lair_slug": _LAIR_SLUG}),
        )

    gm_page.route("**/set_in_lair", _handle)
    gm_page.goto(tabletop_url())

    panel = gm_page.locator("#_lair_action_panel")
    expect(panel).to_be_visible(timeout=5000)

    with gm_page.expect_request("**/set_in_lair"):
        panel.locator("#_lair_toggle_btn").click()
    assert captured.get("in_lair") is True, captured
    assert captured.get("lair_slug") == _LAIR_SLUG, captured


def test_trigger_posts_trigger_lair_action(gm_page: Page):
    """In the in-lair state, clicking a Trigger button opens the
    multi-target picker (stubbed to resolve the hero's id) then POSTs
    /trigger_lair_action with the action_id, lair_slug, and picked
    target ids."""
    _seed_battle(gm_page, in_lair=True)

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
                "lair_slug": _LAIR_SLUG,
                "action_id": "magma-erupts",
                "action_name": "Magma Erupts",
                "damage": 21,
                "damage_type": "fire",
                "results": [],
            }),
        )

    gm_page.route("**/trigger_lair_action", _handle)
    gm_page.goto(tabletop_url())

    panel = gm_page.locator("#_lair_action_panel")
    expect(panel).to_be_visible(timeout=5000)
    # Already in lair (seeded) → action list present.
    expect(panel.locator("._lair_trigger_btn").first).to_be_visible(timeout=3000)

    # Stub the multi-target picker to resolve the hero's combatant id.
    gm_page.evaluate(
        """(heroId) => {
            window.vttOpenMultiTargetPicker = async () => [heroId];
        }""",
        _HERO_ID,
    )

    with gm_page.expect_request("**/trigger_lair_action"):
        panel.locator("._lair_trigger_btn").first.click()
    assert captured.get("action_id") == "magma-erupts", captured
    assert captured.get("lair_slug") == _LAIR_SLUG, captured
    assert captured.get("aoe_target_combatant_ids") == [_HERO_ID], captured


def test_resolved_action_disables_its_trigger_no_repeat(gm_page: Page):
    """v2.172.0 — RAW MM p.11: a lair action can't be used two rounds in a
    row. After a lair_action_resolved broadcast parks the fired action id,
    that action's Trigger button reads "Used last round" and is disabled,
    while the other action stays triggerable."""
    _seed_battle(gm_page, in_lair=True)
    gm_page.goto(tabletop_url())

    panel = gm_page.locator("#_lair_action_panel")
    expect(panel).to_be_visible(timeout=5000)
    expect(panel.locator("._lair_trigger_btn")).to_have_count(2, timeout=3000)
    # Both triggerable to start.
    enabled_before = panel.locator("._lair_trigger_btn:not([disabled])")
    expect(enabled_before).to_have_count(2)

    _dispatch_lair_action_resolved(gm_page, "magma-erupts")

    # Magma's button is now disabled + relabelled; Tremor stays enabled.
    disabled = panel.locator("._lair_trigger_btn[disabled]")
    expect(disabled).to_have_count(1, timeout=3000)
    expect(disabled).to_contain_text("Used last round")
    expect(disabled).to_have_attribute("data-action-id", "magma-erupts")
    expect(panel.locator("._lair_trigger_btn:not([disabled])")).to_have_count(1)
