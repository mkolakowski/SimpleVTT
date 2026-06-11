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


# v2.158.89 — Phase 3c modal UX. Clicking a catalog-action Use
# button now opens an in-page modal (replaces the v2.158.85
# placeholder ``window.prompt``). The HTTP harness covers the
# /use_item_action contract; these UI tests assert the modal opens
# with the right control shape and that submitting / canceling
# works without a browser-native prompt dialog.


def test_pearl_use_button_opens_modal_with_slot_select(gm_page: Page, roster: dict):
    """v2.158.89 Phase 3c: clicking 🔮 Use Pearl opens the
    `#item-action-modal` overlay containing a <select> with options
    L1/L2/L3 (Pearl is a single-action, slot-level item)."""
    thalindra = roster["Thalindra Moonwhisper"]
    page = gm_page
    page.goto(sheet_url(thalindra["id"]))

    pearl_row = page.locator(".inv-row", has_text="Pearl of Power")
    expect(pearl_row).to_be_visible(timeout=5000)
    pearl_row.locator(".inv-item-action").click()

    modal = page.locator("#item-action-modal")
    expect(modal).to_be_visible(timeout=2000)
    expect(modal).to_contain_text("Pearl of Power")

    # The select renders one <option> per slot level 1-3.
    sel = modal.locator("#ia-val")
    expect(sel).to_be_visible()
    expect(sel.locator("option")).to_have_count(3)

    # Cancel dismisses the modal without firing the endpoint.
    modal.locator("#ia-cancel").click()
    expect(modal).to_be_hidden()


def test_wand_use_button_opens_modal_with_charge_spinner(gm_page: Page, roster: dict):
    """v2.158.89 Phase 3c: clicking 🪄 Cast MM opens the modal with
    a numeric input (1-7) and a live cast-Lv preview. The wand cfg's
    `cast_level(n) = n`, so picking 3 → "Cast at Lv 3"."""
    thalindra = roster["Thalindra Moonwhisper"]
    page = gm_page
    page.goto(sheet_url(thalindra["id"]))

    wand_row = page.locator(".inv-row", has_text="Wand of Magic Missiles")
    expect(wand_row).to_be_visible(timeout=5000)
    wand_row.locator(".inv-item-action").click()

    modal = page.locator("#item-action-modal")
    expect(modal).to_be_visible(timeout=2000)
    expect(modal).to_contain_text("Magic Missile")

    spinner = modal.locator("#ia-val")
    expect(spinner).to_be_visible()
    expect(spinner).to_have_attribute("type", "number")
    expect(spinner).to_have_attribute("min", "1")
    expect(spinner).to_have_attribute("max", "7")

    # Initial preview: charges=1 → Lv 1.
    expect(modal.locator("#ia-lvl")).to_have_text("1")
    # Bump charges → preview tracks.
    spinner.fill("3")
    expect(modal.locator("#ia-lvl")).to_have_text("3")

    modal.locator("#ia-cancel").click()
    expect(modal).to_be_hidden()


def test_fireball_wand_modal_shows_base_3_offset(gm_page: Page, roster: dict):
    """v2.158.89 Phase 3c: the Fireball wand's cfg.cast_level(n) =
    n + 2 (base slot 3, charges == slot level - 2). Picking 1 charge
    → "Cast at Lv 3"; 4 charges → "Cast at Lv 6"."""
    thalindra = roster["Thalindra Moonwhisper"]
    page = gm_page
    page.goto(sheet_url(thalindra["id"]))

    wand_row = page.locator(".inv-row", has_text="Wand of Fireballs")
    expect(wand_row).to_be_visible(timeout=5000)
    wand_row.locator(".inv-item-action").click()

    modal = page.locator("#item-action-modal")
    expect(modal).to_be_visible(timeout=2000)
    expect(modal).to_contain_text("Fireball")

    spinner = modal.locator("#ia-val")
    # 1 charge → Lv 3 (base).
    expect(modal.locator("#ia-lvl")).to_have_text("3")
    # 4 charges → Lv 6.
    spinner.fill("4")
    expect(modal.locator("#ia-lvl")).to_have_text("6")

    modal.locator("#ia-cancel").click()
    expect(modal).to_be_hidden()


# v2.158.90 — Phase 3d: Staff of Healing 2-stage modal. The staff is
# the first multi-action catalog item — the modal pops an action
# picker (Cure Wounds / Lesser Restoration / Mass Cure Wounds) before
# the charge spinner appears. Tests run against Tavik, who carries
# the staff (equipped + attuned) in his v2.158.88 seed.


def test_staff_use_button_renders(gm_page: Page, roster: dict):
    """v2.158.90: Tavik's inventory shows a 🩹 Use Staff button on
    the Staff of Healing row (catalog-action item, equipped, attuned)."""
    tavik = roster["Brother Tavik Stonebrow"]
    page = gm_page
    page.goto(sheet_url(tavik["id"]))

    staff_row = page.locator(".inv-row", has_text="Staff of Healing")
    expect(staff_row).to_be_visible(timeout=5000)

    btn = staff_row.locator(".inv-item-action")
    expect(btn).to_be_visible()
    expect(btn).to_contain_text("Staff")


def test_staff_use_button_opens_action_picker_modal(gm_page: Page, roster: dict):
    """v2.158.90 Phase 3d: clicking 🩹 Use Staff opens the modal
    with 3 radio options (one per staff action). The charge block is
    hidden + the submit button is disabled until an action is picked."""
    tavik = roster["Brother Tavik Stonebrow"]
    page = gm_page
    page.goto(sheet_url(tavik["id"]))

    staff_row = page.locator(".inv-row", has_text="Staff of Healing")
    expect(staff_row).to_be_visible(timeout=5000)
    staff_row.locator(".inv-item-action").click()

    modal = page.locator("#item-action-modal")
    expect(modal).to_be_visible(timeout=2000)
    expect(modal).to_contain_text("Staff of Healing")

    # 3 action radios.
    radios = modal.locator('input[name="ia-action"]')
    expect(radios).to_have_count(3)
    expect(modal).to_contain_text("Cure Wounds")
    expect(modal).to_contain_text("Lesser Restoration")
    expect(modal).to_contain_text("Mass Cure Wounds")

    # Charge block hidden + submit disabled before a pick.
    expect(modal.locator("#ia-charge-block")).to_be_hidden()
    expect(modal.locator("#ia-confirm")).to_be_disabled()

    modal.locator("#ia-cancel").click()
    expect(modal).to_be_hidden()


def test_staff_pick_cure_wounds_shows_variable_spinner(gm_page: Page, roster: dict):
    """v2.158.90 Phase 3d: picking Cure Wounds reveals a charge
    spinner with min=1 max=4 (the variable-charge case) and a live
    "Cast at Lv X" preview. cast_level(1)=1, cast_level(3)=3."""
    tavik = roster["Brother Tavik Stonebrow"]
    page = gm_page
    page.goto(sheet_url(tavik["id"]))

    staff_row = page.locator(".inv-row", has_text="Staff of Healing")
    expect(staff_row).to_be_visible(timeout=5000)
    staff_row.locator(".inv-item-action").click()

    modal = page.locator("#item-action-modal")
    expect(modal).to_be_visible(timeout=2000)

    # Pick Cure Wounds (the first action).
    modal.locator("#ia-act-0").check()

    spinner = modal.locator("#ia-val")
    expect(spinner).to_be_visible()
    expect(spinner).to_have_attribute("min", "1")
    expect(spinner).to_have_attribute("max", "4")
    expect(spinner).to_have_value("1")

    # Default 1 charge → Lv 1.
    expect(modal.locator("#ia-lvl")).to_have_text("1")
    # 3 charges → Lv 3.
    spinner.fill("3")
    expect(modal.locator("#ia-lvl")).to_have_text("3")

    # Confirm now enabled.
    expect(modal.locator("#ia-confirm")).to_be_enabled()
    modal.locator("#ia-cancel").click()
    expect(modal).to_be_hidden()


def test_staff_pick_lesser_restoration_locks_at_2(gm_page: Page, roster: dict):
    """v2.158.90 Phase 3d: picking Lesser Restoration (fixed-charge
    action) renders the spinner readonly at value=2 (min==max==2).
    Preview reads the spell name with implicit Lv 2 in parens."""
    tavik = roster["Brother Tavik Stonebrow"]
    page = gm_page
    page.goto(sheet_url(tavik["id"]))

    staff_row = page.locator(".inv-row", has_text="Staff of Healing")
    expect(staff_row).to_be_visible(timeout=5000)
    staff_row.locator(".inv-item-action").click()

    modal = page.locator("#item-action-modal")
    expect(modal).to_be_visible(timeout=2000)

    # Pick Lesser Restoration (the second action).
    modal.locator("#ia-act-1").check()

    spinner = modal.locator("#ia-val")
    expect(spinner).to_have_attribute("min", "2")
    expect(spinner).to_have_attribute("max", "2")
    expect(spinner).to_have_value("2")
    expect(spinner).to_have_attribute("readonly", "")

    # Preview reads the spell name + implicit Lv 2.
    expect(modal.locator("#ia-preview")).to_contain_text("Lesser Restoration")
    expect(modal.locator("#ia-preview")).to_contain_text("Lv 2")

    modal.locator("#ia-cancel").click()
    expect(modal).to_be_hidden()


# v2.158.94 — Phase 5d: Flame Tongue ignite/extinguish 1-click
# button. Different shape from Phase 3c/3d modals — there's no
# parameter to ask for, just a state flip. Button label adapts to
# Garrik's Flame Tongue's current `_lit` field.


def _force_garrik_flame_tongue_lit(char_id: int, lit: bool) -> None:
    """Force Garrik's Flame Tongue to a known state via the API.
    Used by the Phase 5d tests to neutralize prior _lit state left
    behind by the test_flame_tongue_ignite.py HTTP harness when both
    suites run against the same shared container."""
    import httpx
    with httpx.Client(
        base_url="http://localhost:8013", follow_redirects=True,
    ) as c:
        c.post(
            "/login",
            data={"email": "demo-gm@example.com", "password": "demopass"},
        )
        action_key = "ignite" if lit else "extinguish"
        # 409 (no_state_change) is fine — means already in the
        # desired state.
        c.post(
            f"/api/campaign/1/character/{char_id}/use_item_action",
            json={"inventory_index": 7, "action_key": action_key},
        )


def test_flame_tongue_use_button_renders(gm_page: Page, roster: dict):
    """v2.158.94: Garrik's inventory shows the Flame Tongue 1-click
    toggle button. Force-lit before asserting so prior tests that
    may have left the staff extinguished don't poison the assertion."""
    garrik = roster["Garrik Ironside"]
    _force_garrik_flame_tongue_lit(garrik["id"], True)

    page = gm_page
    page.goto(sheet_url(garrik["id"]))

    ft_row = page.locator(".inv-row", has_text="Flame Tongue Longsword")
    expect(ft_row).to_be_visible(timeout=5000)

    btn = ft_row.locator(".inv-item-action")
    expect(btn).to_be_visible()
    expect(btn).to_contain_text("Extinguish")


# v2.159.6 — Phase 8f: Javelin of Lightning aoe-line wire-up.
# Krieger gets a ⚡ Hurl Lightning button on his inventory row.
# Click triggers a 2-stage flow: single-target picker → call
# /battle/line-targets → window.confirm → POST /use_item_action.
# v1 test scope is just the render; the full submit chain wraps
# vttOpenMultiTargetPicker which needs a live battle + map.


def test_aoe_line_confirm_modal_renders_combatant_list(
    gm_page: Page, roster: dict,
):
    """v2.159.7 Phase 8g: the _showAoELineConfirmModal helper renders
    a checkbox-per-combatant list, lets the GM uncheck targets to
    opt them out, and resolves to the final id list on Confirm. Test
    invokes the helper directly via page.evaluate so we don't need a
    live battle / positioned tokens.

    Navigates to Krieger's sheet (so sheet_dnd5e.html's script
    block is loaded), then injects a synthetic cfg + promise to
    drive the modal."""
    krieger = roster["Krieger Stonefist"]
    page = gm_page
    page.goto(sheet_url(krieger["id"]))

    # Open the modal with 2 synthetic combatants. Wrap in an IIFE
    # that returns nothing so page.evaluate doesn't await the
    # modal's promise (which only resolves on user interaction).
    # page.evaluate awaits the returned value. To fire the modal
    # without blocking, install an onload-style queued task using
    # setTimeout(fn, 0). The evaluate returns immediately; the modal
    # is then triggered + its returned promise is captured into
    # window._aoeTestPicked when the user (test) interacts.
    page.evaluate("""
        window._aoeTestPicked = null;
        setTimeout(async () => {
            window._aoeTestPicked = await window._showAoELineConfirmModal({
                title: '⚡ Test',
                body: 'Test body copy',
                combatants: [
                    {combatant_id: 'tok_A', name: 'Goblin A', distance_ft: 5.0},
                    {combatant_id: 'tok_B', name: 'Goblin B', distance_ft: 15.0},
                ],
                submit_label: '⚡ Fire Test',
            });
        }, 0);
    """)

    modal = page.locator("#aoe-line-confirm-modal")
    expect(modal).to_be_visible(timeout=2000)
    expect(modal).to_contain_text("Goblin A")
    expect(modal).to_contain_text("Goblin B")
    expect(modal).to_contain_text("5.0 ft")
    expect(modal).to_contain_text("15.0 ft")
    # All checkboxes start checked.
    cbs = modal.locator(".aoe-tgt-cb")
    expect(cbs).to_have_count(2)

    # Uncheck Goblin B (index 1).
    modal.locator("#aoe-cb-1").uncheck()

    # Click Fire.
    modal.locator("#aoe-confirm").click()
    expect(modal).to_be_hidden()

    # The promise should have resolved to ['tok_A'] only.
    result = page.evaluate("window._aoeTestPicked")
    assert result == ["tok_A"], (
        f"Modal should return only the checked combatants; got {result}"
    )


def test_aoe_line_confirm_modal_cancel_returns_null(
    gm_page: Page, roster: dict,
):
    """v2.159.7: cancel button → modal closes, promise resolves to
    null."""
    krieger = roster["Krieger Stonefist"]
    page = gm_page
    page.goto(sheet_url(krieger["id"]))

    page.evaluate("""
        window._aoeTestPicked = 'untouched';
        setTimeout(async () => {
            window._aoeTestPicked = await window._showAoELineConfirmModal({
                title: '⚡ Cancel test',
                body: 'Should resolve to null',
                combatants: [
                    {combatant_id: 'tok_X', name: 'Bandit', distance_ft: 2.5},
                ],
            });
        }, 0);
    """)
    modal = page.locator("#aoe-line-confirm-modal")
    expect(modal).to_be_visible(timeout=2000)

    modal.locator("#aoe-cancel").click()
    expect(modal).to_be_hidden()
    result = page.evaluate("window._aoeTestPicked")
    assert result is None, (
        f"Cancel should resolve to null; got {result!r}"
    )


def test_javelin_lightning_click_fires_use_item_action(
    gm_page: Page, roster: dict,
):
    """v2.159.8 Phase 8h: end-to-end Javelin click chain.
    Click ⚡ Hurl Lightning → stubbed vttOpenMultiTargetPicker returns
    a single target id → /battle/line-targets returns auto-picked
    combatants → AoE confirm modal opens → click Fire → POST
    /use_item_action with the right body → sheet's _used_today flag
    flips and the button relabels to ⚡ (spent until dawn).

    Stubs:
      - vttOpenMultiTargetPicker: returns [targetCid] immediately
      - /battle: returns a synthetic combatant list so the click
        handler finds Krieger's combatant id without needing a real
        battle to be seeded
      - /battle/line-targets: returns a 1-combatant result so the
        modal renders something to confirm
    """
    import httpx, json
    krieger = roster["Krieger Stonefist"]

    # Force-rest so the javelin starts un-spent regardless of test
    # order.
    with httpx.Client(
        base_url="http://localhost:8013", follow_redirects=True,
    ) as c:
        c.post(
            "/login",
            data={"email": "demo-gm@example.com", "password": "demopass"},
        )
        c.post(
            f"/api/campaign/1/character/{krieger['id']}/rest",
            json={"type": "long"},
        )

    page = gm_page
    # Intercept /api/campaign/1/battle (GET — find caster) +
    # /battle/line-targets (POST — auto-pick combatants) so the test
    # doesn't depend on a live battle. The /use_item_action POST is
    # NOT intercepted — we want the real endpoint to flip the flag.
    def _handle_battle(route):
        if route.request.method == "GET":
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({
                    "battle": {
                        "combatants": [
                            {"id": "tok_test_krieger", "char_id": krieger["id"], "name": krieger["name"], "source_token_id": 1},
                            {"id": "tok_test_target", "name": "Bandit", "source_token_id": 2},
                            {"id": "tok_test_extra", "name": "Goblin", "source_token_id": 3},
                        ],
                    },
                }),
            )
        else:
            route.continue_()
    page.route("**/api/campaign/1/battle", _handle_battle)

    def _handle_line(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({
                "caster_id": "tok_test_krieger",
                "target_id": "tok_test_target",
                "width_ft": 5,
                "max_length_ft": 120,
                "results": [
                    {"combatant_id": "tok_test_extra", "name": "Goblin", "distance_ft": 4.0},
                ],
            }),
        )
    page.route("**/api/campaign/1/battle/line-targets", _handle_line)

    page.goto(sheet_url(krieger["id"]))

    # Stub the global single-target picker BEFORE clicking the
    # button. The picker normally renders on the tabletop; for this
    # sheet-only test we just resolve immediately with a known id.
    page.evaluate("""
        window.vttOpenMultiTargetPicker = async () => ['tok_test_target'];
    """)

    jav_row = page.locator(".inv-row", has_text="Javelin of Lightning")
    expect(jav_row).to_be_visible(timeout=5000)
    jav_btn = jav_row.locator(".inv-item-action")
    expect(jav_btn).to_contain_text("Hurl Lightning")

    # Wait for the use_item_action POST so we can confirm the right
    # body was sent.
    with page.expect_request(
        lambda req: (
            req.url.endswith(f"/use_item_action")
            and req.method == "POST"
        ),
        timeout=10000,
    ) as req_info:
        jav_btn.click()
        # Confirm modal should appear.
        modal = page.locator("#aoe-line-confirm-modal")
        expect(modal).to_be_visible(timeout=5000)
        expect(modal).to_contain_text("Goblin")
        modal.locator("#aoe-confirm").click()

    posted = req_info.value
    payload = posted.post_data_json
    assert payload["action_key"] == "hurl-lightning", payload
    assert payload["target_combatant_ids"] == ["tok_test_extra"], payload
    assert payload.get("inventory_index") == 5  # Krieger's javelin idx

    # The real server flipped _used_today: True. Button should now
    # relabel to ⚡ (spent until dawn) after the local renderInventory.
    expect(jav_btn).to_contain_text("spent until dawn", timeout=5000)


def test_javelin_lightning_button_renders_when_unspent(
    gm_page: Page, roster: dict,
):
    """v2.159.6: Krieger's Javelin of Lightning inventory row shows
    a ⚡ Hurl Lightning button. Seed-default `_used_today: False` so
    the button renders enabled (not the disabled `_(spent until dawn)`
    label).

    NOTE: this test assumes the demo seed's Krieger has the javelin
    with _used_today: False. If a prior test left him spent, force
    a long rest via the API first."""
    import httpx
    krieger = roster["Krieger Stonefist"]
    # Force-rest Krieger so the javelin is un-spent regardless of
    # prior test order.
    with httpx.Client(
        base_url="http://localhost:8013", follow_redirects=True,
    ) as c:
        c.post(
            "/login",
            data={"email": "demo-gm@example.com", "password": "demopass"},
        )
        c.post(
            f"/api/campaign/1/character/{krieger['id']}/rest",
            json={"type": "long"},
        )

    page = gm_page
    page.goto(sheet_url(krieger["id"]))

    jav_row = page.locator(".inv-row", has_text="Javelin of Lightning")
    expect(jav_row).to_be_visible(timeout=5000)

    btn = jav_row.locator(".inv-item-action")
    expect(btn).to_be_visible()
    # Seed default un-spent → enabled, label "⚡ Hurl Lightning".
    expect(btn).to_contain_text("Hurl Lightning")
    expect(btn).to_be_enabled()


def test_flame_tongue_click_toggles_label_and_relabels(gm_page: Page, roster: dict):
    """v2.158.94: clicking the Extinguish button flips the label to
    🔥 Ignite (and the underlying _lit state to false). Then clicking
    again flips back to ❄ Extinguish, restoring the lit state."""
    garrik = roster["Garrik Ironside"]
    _force_garrik_flame_tongue_lit(garrik["id"], True)

    page = gm_page
    page.goto(sheet_url(garrik["id"]))

    ft_row = page.locator(".inv-row", has_text="Flame Tongue Longsword")
    expect(ft_row).to_be_visible(timeout=5000)

    btn = ft_row.locator(".inv-item-action")
    expect(btn).to_contain_text("Extinguish")

    try:
        # First click: extinguish → label flips to Ignite.
        btn.click()
        expect(btn).to_contain_text("Ignite", timeout=3000)

        # Second click: ignite → label flips back to Extinguish.
        btn.click()
        expect(btn).to_contain_text("Extinguish", timeout=3000)
    finally:
        # Hard-force lit so downstream tests see Garrik with the
        # seed-default state regardless of which click path failed.
        _force_garrik_flame_tongue_lit(garrik["id"], True)
