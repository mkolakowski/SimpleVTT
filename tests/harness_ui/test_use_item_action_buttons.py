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
