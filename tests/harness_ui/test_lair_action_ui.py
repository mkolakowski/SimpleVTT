"""v2.170.0 — lair-action Phase 3c UI on the GM tabletop.

The HTTP harness `tests/harness/test_trigger_lair_action.py` covers the
endpoint contracts (`/set_in_lair`, `/trigger_lair_action`, the AoE
save dispatch, the carry-forward guard). This file covers the
browser-side surface v2.170.0 adds to `tabletop.html`:

  - When the active battle holds a combatant carrying a non-empty
    `lair_actions` list, the GM sees the 🌋 lair-action panel
    (`#_lair_action_panel`) with an Enter/Exit toggle. As of v2.862.0 the
    panel lives INSIDE the Battle drawer (`#players-drawer`), under the
    Reactions panel, rather than floating over the map.
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


def _battle_json(in_lair: bool = False, turn_index: int = 0,
                 regional_fade=None) -> str:
    """A Hero (init 25) + an Ancient Red Dragon (init 20) carrying two
    pre-baked lair actions and a lair_slug. `turn_index` selects the
    active combatant: 0 = Hero (init 25 > 20), 1 = Dragon (init 20 ≤ 20,
    i.e. initiative count 20 reached). `regional_fade` (v2.182.0) seeds
    the fade-tracker state on the battle dict."""
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
                "regional_effects": [
                    {
                        "id": "minor-earthquakes",
                        "name": "Minor Earthquakes",
                        "desc": "Small earthquakes are common within 6 miles of the lair.",
                    },
                    {
                        "id": "fouled-water",
                        "name": "Warm, Foul Water",
                        "desc": "Water sources within 1 mile are supernaturally warm and tainted by sulfur.",
                    },
                ],
            },
        ],
        "turn_index": turn_index,
        "round": 1,
        "active": True,
        "in_lair": in_lair,
        "lair_slug": _LAIR_SLUG if in_lair else "",
        "regional_fade": regional_fade,
    })


def _seed_battle(page: Page, in_lair: bool = False, turn_index: int = 0,
                 regional_fade=None) -> None:
    page.add_init_script(
        f"window.localStorage.setItem('simplevtt_battle_{CAMPAIGN_ID}', "
        f"{json.dumps(_battle_json(in_lair, turn_index, regional_fade))});"
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


def _dispatch_lair_action_resolved(page: Page, action_id: str,
                                   acted_round=None) -> None:
    page.evaluate(
        """(args) => {
            const data = {
                action_id: args.actionId,
                action_name: 'Magma Erupts',
                last_lair_action_id: args.actionId,
                results: [],
            };
            if (args.actedRound !== null) data.lair_acted_round = args.actedRound;
            document.dispatchEvent(new CustomEvent('vtt:ws-message', {detail: {
                type: 'lair_action_resolved', data,
            }}));
        }""",
        {"actionId": action_id, "actedRound": acted_round},
    )


def test_lair_panel_toggle_renders(gm_page: Page):
    """When the battle holds a lair-bearing creature, the GM sees the
    lair-action panel with an "Enter lair" toggle and no action
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


def test_lair_panel_lives_in_battle_drawer(gm_page: Page):
    """v2.862.0 — the lair-action panel is a descendant of the Battle
    drawer (`#players-drawer`), directly under the Reactions panel — NOT a
    floating card appended to <body>. Regression guard for the relocation."""
    _seed_battle(gm_page, in_lair=False)
    gm_page.goto(tabletop_url())

    # The scoped selector only matches if the panel is inside the drawer.
    scoped = gm_page.locator("#players-drawer #_lair_action_panel")
    expect(scoped).to_be_visible(timeout=5000)
    expect(scoped).to_contain_text("Lair Actions")

    # It is NOT a direct child of <body> (the old floating position).
    parent_tag = gm_page.evaluate(
        "() => (document.getElementById('_lair_action_panel')?.parentElement?.tagName || '').toLowerCase()"
    )
    assert parent_tag not in ("", "body"), (
        f"lair panel should sit inside the drawer, not <body> (parent=<{parent_tag}>)"
    )
    # And it sits after the Reactions panel in the drawer's DOM order.
    order = gm_page.evaluate(
        """() => {
            const drawer = document.getElementById('players-drawer');
            const nodes = [...drawer.querySelectorAll('#gm-reactions-panel, #_lair_action_panel')];
            return nodes.map(n => n.id);
        }"""
    )
    assert order == ["gm-reactions-panel", "_lair_action_panel"], order


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


def test_resolved_action_disables_all_triggers_once_per_round(gm_page: Page):
    """v2.173.0 — RAW MM p.11: one lair action per round. When a
    lair_action_resolved broadcast carries `lair_acted_round` matching the
    battle's round, EVERY Trigger button is disabled + relabelled "Acted
    this round" and an "already acted this round" banner is shown."""
    _seed_battle(gm_page, in_lair=True)
    gm_page.goto(tabletop_url())

    panel = gm_page.locator("#_lair_action_panel")
    expect(panel).to_be_visible(timeout=5000)
    expect(panel.locator("._lair_trigger_btn")).to_have_count(2, timeout=3000)
    expect(panel.locator("._lair_trigger_btn:not([disabled])")).to_have_count(2)

    # Battle is seeded at round 1; mark the lair as having acted this round.
    _dispatch_lair_action_resolved(gm_page, "magma-erupts", acted_round=1)

    # Both triggers now disabled + relabelled; banner shown.
    disabled = panel.locator("._lair_trigger_btn[disabled]")
    expect(disabled).to_have_count(2, timeout=3000)
    expect(disabled.first).to_contain_text("Acted this round")
    expect(panel).to_contain_text("Lair already acted this round")


def test_init_20_banner_surfaces_when_reached(gm_page: Page):
    """v2.174.0 — RAW MM p.11: lair actions fire on initiative count 20.
    With the Dragon (init 20) as the active combatant, the panel surfaces
    the "Initiative count 20 — … acts now" prompt; with the Hero (init 25)
    active it shows the "not yet reached" hint instead."""
    # turn_index=1 → Dragon (init 20) active → init count 20 reached.
    _seed_battle(gm_page, in_lair=True, turn_index=1)
    gm_page.goto(tabletop_url())

    panel = gm_page.locator("#_lair_action_panel")
    expect(panel).to_be_visible(timeout=5000)
    expect(panel).to_contain_text("Initiative count 20", timeout=3000)
    expect(panel).to_contain_text("acts now")
    # Triggers stay enabled (prompt, not gate).
    expect(panel.locator("._lair_trigger_btn:not([disabled])")).to_have_count(2)

    # turn_index=0 → Hero (init 25) active → count 20 not yet reached.
    _seed_battle(gm_page, in_lair=True, turn_index=0)
    gm_page.goto(tabletop_url())
    panel = gm_page.locator("#_lair_action_panel")
    expect(panel).to_be_visible(timeout=5000)
    expect(panel).to_contain_text("not yet reached", timeout=3000)


def _dispatch_lair_init_20_reached(page: Page) -> None:
    page.evaluate(
        """(slug) => {
            document.dispatchEvent(new CustomEvent('vtt:ws-message', {detail: {
                type: 'lair_init_20_reached',
                data: {lair_slug: slug, owner_name: 'Ancient Red Dragon', round: 1},
            }}));
        }""",
        _LAIR_SLUG,
    )


def test_init_20_player_gets_flavor_toast(alice_page: Page):
    """v2.176.0 — RAW MM p.11: a player (non-GM) receiving the
    `lair_init_20_reached` broadcast sees an atmospheric "The lair stirs…"
    toast — no GM-only mechanics (owner name / "may take a lair action")."""
    _seed_battle(alice_page, in_lair=True, turn_index=1)
    alice_page.goto(tabletop_url())

    _dispatch_lair_init_20_reached(alice_page)

    toast = alice_page.locator(".vtt-toast").filter(has_text="The lair stirs")
    expect(toast).to_be_visible(timeout=3000)
    # The player must NOT see the GM-only mechanical phrasing.
    expect(alice_page.locator(".vtt-toast").filter(
        has_text="may take a lair action")).to_have_count(0)


def test_init_20_gm_gets_mechanical_toast(gm_page: Page):
    """v2.176.0 — the GM still gets the mechanical nudge naming the owner
    and "may take a lair action" (not the player flavor cue)."""
    _seed_battle(gm_page, in_lair=True, turn_index=1)
    gm_page.goto(tabletop_url())

    _dispatch_lair_init_20_reached(gm_page)

    toast = gm_page.locator(".vtt-toast").filter(has_text="may take a lair action")
    expect(toast).to_be_visible(timeout=3000)
    expect(toast).to_contain_text("Ancient Red Dragon")


def _dispatch_lair_action_resolved_full(page: Page) -> None:
    """Dispatch a fully-populated lair_action_resolved (the v2.177.0
    broadcast shape) carrying owner_name + per-target results so the
    roll-log card renders its header + save line + pills."""
    page.evaluate(
        """(slug) => {
            document.dispatchEvent(new CustomEvent('vtt:ws-message', {detail: {
                type: 'lair_action_resolved',
                data: {
                    lair_slug: slug,
                    owner_name: 'Ancient Red Dragon',
                    action_id: 'magma-erupts',
                    action_name: 'Magma Erupts',
                    save_ability: 'DEX',
                    save_dc: 15,
                    damage: '6d6',
                    damage_type: 'fire',
                    half_on_save: true,
                    effect: '',
                    results: [
                        {combatant_id: 'a', name: 'Bandit One', passed: false,
                         prompted: false, damage_dealt: 17, condition_installed: false},
                        {combatant_id: 'b', name: 'Bandit Two', passed: true,
                         prompted: false, damage_dealt: 0, condition_installed: false},
                    ],
                    last_lair_action_id: 'magma-erupts',
                    lair_acted_round: 1,
                },
            }}));
        }""",
        _LAIR_SLUG,
    )


def test_lair_action_resolved_renders_roll_log_card(gm_page: Page):
    """v2.177.0 — a lair_action_resolved broadcast renders a persistent
    roll-log card (#roll-list) headed by the owner + "Lair Action" with the
    action name, save line, and one result pill per target (❌ with damage
    for a failed save, ✅ saved for a passed one)."""
    _seed_battle(gm_page, in_lair=True, turn_index=1)
    gm_page.goto(tabletop_url())

    _dispatch_lair_action_resolved_full(gm_page)

    # The roll-log drawer is collapsed by default, so the card is in the
    # DOM but not "visible" — assert on presence + text content.
    card = gm_page.locator("#roll-list .feature-used-card", has_text="Magma Erupts")
    expect(card).to_have_count(1, timeout=3000)
    expect(card).to_contain_text("Lair Action")
    expect(card).to_contain_text("Ancient Red Dragon")
    expect(card).to_contain_text("DEX save · DC 15")
    # Failed save → red pill carrying the damage + type.
    failed = card.locator(".result-pill.chip-miss")
    expect(failed).to_contain_text("Bandit One")
    expect(failed).to_contain_text("17")
    expect(failed).to_contain_text("fire")
    # Passed save → green saved pill.
    expect(card.locator(".result-pill.chip-hit")).to_contain_text("Bandit Two")


def test_regional_effects_render_in_panel(gm_page: Page):
    """v2.179.0 — the lair-action panel lists the lair's passive regional
    effects (RAW MM p.11) under a "Regional Effects" heading. They render
    whenever the lair owner is on the field — no Enter-lair toggle needed —
    since they radiate while the creature dwells in its lair."""
    # Out of lair: regional effects still show (they're passive/always-on).
    _seed_battle(gm_page, in_lair=False)
    gm_page.goto(tabletop_url())

    panel = gm_page.locator("#_lair_action_panel")
    expect(panel).to_be_visible(timeout=5000)
    expect(panel).to_contain_text("Regional Effects", timeout=3000)
    expect(panel).to_contain_text("Minor Earthquakes")
    expect(panel).to_contain_text("Warm, Foul Water")
    expect(panel).to_contain_text("supernaturally warm")
    # No Enter-lair toggle needed — regional effects render out of lair too.
    expect(panel.locator("#_lair_toggle_btn")).to_contain_text("Enter lair")


def test_regional_effects_render_for_player(alice_page: Page):
    """v2.180.0 — a player (non-GM) sees a read-only regional-effects card
    (#_regional_effects_panel) with the lair's passive effects, but NOT the
    GM lair-action panel (#_lair_action_panel) and NOT the creature's name
    (the panel is atmosphere, not a monster reveal). The player receives the
    lair owner via the GM's `battle_update` broadcast (the real sync path —
    a player's localStorage seed is overwritten by that broadcast)."""
    alice_page.goto(tabletop_url())

    # Mirror real play: the GM's battle (carrying the dragon's regional
    # effects) reaches the player as a `battle_update` WS broadcast.
    alice_page.evaluate(
        """(battleJson) => {
            document.dispatchEvent(new CustomEvent('vtt:ws-message', {detail: {
                type: 'battle_update', data: JSON.parse(battleJson),
            }}));
        }""",
        _battle_json(in_lair=True, turn_index=1),
    )

    player_panel = alice_page.locator("#_regional_effects_panel")
    expect(player_panel).to_be_visible(timeout=5000)
    expect(player_panel).to_contain_text("Regional Effects")
    expect(player_panel).to_contain_text("Minor Earthquakes")
    expect(player_panel).to_contain_text("supernaturally warm")
    # Players never see the GM lair-action panel or the creature's name.
    expect(alice_page.locator("#_lair_action_panel")).to_have_count(0)
    expect(player_panel).not_to_contain_text("Ancient Red Dragon")
    # No GM-only trigger controls leak into the player card.
    expect(player_panel.locator("._lair_trigger_btn")).to_have_count(0)


def _dispatch_regional_fade_changed(page: Page, regional_fade) -> None:
    page.evaluate(
        """(fade) => {
            document.dispatchEvent(new CustomEvent('vtt:ws-message', {detail: {
                type: 'regional_fade_changed',
                data: {regional_fade: fade},
            }}));
        }""",
        regional_fade,
    )


def test_fade_start_button_renders_and_posts(gm_page: Page):
    """v2.182.0 — with a lair owner carrying regional effects and no fade
    in progress, the GM panel shows a "🕯️ Regional Fade" block with a
    "Start fade" button. Clicking it POSTs /set_regional_fade {action:
    start, lair_slug}."""
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
            body=json.dumps({"ok": True, "regional_fade": {
                "lair_slug": _LAIR_SLUG, "days_total": 6,
                "days_remaining": 6, "faded": False}}),
        )

    gm_page.route("**/set_regional_fade", _handle)
    gm_page.goto(tabletop_url())

    panel = gm_page.locator("#_lair_action_panel")
    expect(panel).to_be_visible(timeout=5000)
    expect(panel).to_contain_text("Regional Fade", timeout=3000)
    start_btn = panel.locator("#_fade_start_btn")
    expect(start_btn).to_be_visible()

    with gm_page.expect_request("**/set_regional_fade"):
        start_btn.click()
    assert captured.get("action") == "start", captured
    assert captured.get("lair_slug") == _LAIR_SLUG, captured


def test_fade_changed_shows_countdown_and_controls(gm_page: Page):
    """v2.182.0 — a regional_fade_changed WS message carrying an active
    fade flips the panel to the days-remaining readout with Advance + Clear
    controls (and no Start button)."""
    _seed_battle(gm_page, in_lair=False)
    gm_page.goto(tabletop_url())

    panel = gm_page.locator("#_lair_action_panel")
    expect(panel).to_be_visible(timeout=5000)
    expect(panel.locator("#_fade_start_btn")).to_be_visible(timeout=3000)

    _dispatch_regional_fade_changed(gm_page, {
        "lair_slug": _LAIR_SLUG, "days_total": 6,
        "days_remaining": 4, "faded": False,
    })

    expect(panel).to_contain_text("4 / 6 days remaining", timeout=3000)
    expect(panel.locator("#_fade_advance_btn")).to_be_visible()
    expect(panel.locator("#_fade_clear_btn")).to_be_visible()
    expect(panel.locator("#_fade_start_btn")).to_have_count(0)


def test_fade_faded_state_hides_advance(gm_page: Page):
    """v2.182.0 — when the countdown reaches faded=True the readout reads
    "have faded" and the Advance button is gone (only Clear remains)."""
    _seed_battle(gm_page, in_lair=False)
    gm_page.goto(tabletop_url())

    panel = gm_page.locator("#_lair_action_panel")
    expect(panel).to_be_visible(timeout=5000)

    _dispatch_regional_fade_changed(gm_page, {
        "lair_slug": _LAIR_SLUG, "days_total": 6,
        "days_remaining": 0, "faded": True,
    })

    expect(panel).to_contain_text("have faded", timeout=3000)
    expect(panel.locator("#_fade_advance_btn")).to_have_count(0)
    expect(panel.locator("#_fade_clear_btn")).to_be_visible()


def test_fade_player_gets_atmospheric_cue(alice_page: Page):
    """v2.182.0 — a player whose battle carries an active regional_fade
    sees an italic 🕯️ cue on their regional-effects card (no day numbers,
    no controls)."""
    alice_page.goto(tabletop_url())

    alice_page.evaluate(
        """(battleJson) => {
            document.dispatchEvent(new CustomEvent('vtt:ws-message', {detail: {
                type: 'battle_update', data: JSON.parse(battleJson),
            }}));
        }""",
        _battle_json(in_lair=True, turn_index=1, regional_fade={
            "lair_slug": _LAIR_SLUG, "days_total": 6,
            "days_remaining": 3, "faded": False,
        }),
    )

    player_panel = alice_page.locator("#_regional_effects_panel")
    expect(player_panel).to_be_visible(timeout=5000)
    expect(player_panel).to_contain_text("waning", timeout=3000)
    # No GM day-count numbers or controls leak to the player.
    expect(player_panel).not_to_contain_text("days remaining")
    expect(player_panel.locator("#_fade_advance_btn")).to_have_count(0)
