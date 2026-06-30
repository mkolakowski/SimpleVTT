"""v2.763.0 — multi-map encounters: the settings linked-maps picker.

The encounter editor in campaign settings now has a multi-select for an
encounter's linked maps (saved as `linked_map_ids` via the PATCH endpoint).
This drives the real editor: open an encounter, the linked-maps picker shows.
"""
from __future__ import annotations

from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def test_encounter_editor_has_linked_maps_picker(gm_page: Page) -> None:
    errors: list[str] = []
    gm_page.on("pageerror", lambda e: errors.append(str(e)))
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/settings")

    # The encounters section lives in the "World" tab.
    gm_page.locator('.settings-tab[data-tab="world"]').click()
    # Wait for the section to become visible (tab switch) + the library to
    # render its client-side cards.
    gm_page.wait_for_function(
        "() => { const s = document.getElementById('encounters');"
        " return s && getComputedStyle(s).display !== 'none'"
        " && document.querySelectorAll('#enc-library button').length > 0; }",
        timeout=8000)
    # Encounter cards may be grouped inside collapsed <details> — open them.
    gm_page.evaluate(
        "() => document.querySelectorAll('#enc-library details')"
        ".forEach(d => { d.open = true; })")

    edit_btn = gm_page.locator("#enc-library button", has_text="Edit").first
    expect(edit_btn).to_be_visible(timeout=5000)
    edit_btn.click()

    # The linked-maps multi-select + its label appear in the editor.
    expect(
        gm_page.locator("#enc-library", has_text="Linked maps")
    ).to_be_visible()
    picker = gm_page.locator("#enc-library select[multiple]")
    expect(picker.first).to_be_visible()
    # It lists the campaign's maps as options.
    assert picker.first.locator("option").count() >= 1

    assert not errors, f"JS errors: {errors}"
