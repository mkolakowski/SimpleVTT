"""Phase 5a — the Notes drawer (GM prep notes) in a real browser.

docs/plans/notes-and-handouts.md. Drives notes.js through Playwright:
the GM opens the Notes tab, creates a prep note via the composer, sees
the card render, edits it, and deletes it — with no JS console errors.

GM = gm_page (authenticated GM context on the tabletop).
"""
import re

from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def _open_notes(page: Page):
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    resp = page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
    assert resp is not None and resp.ok, "tabletop failed to load"
    # The Notes tab is auto-wired by the drawer system (data-target).
    tab = page.locator('.drawer-tab-btn[data-target="notes-drawer"]')
    expect(tab).to_be_visible(timeout=5000)
    tab.click()
    # the drawer system adds .open to the active panel
    expect(page.locator("#notes-drawer")).to_have_class(
        re.compile(r"\bopen\b"), timeout=3000)
    return errors


def test_gm_prep_note_create_edit_delete(gm_page: Page):
    errors = _open_notes(gm_page)
    body = gm_page.locator("#notes-body")

    # Clear any pre-existing prep notes via the UI so the assertions
    # below are deterministic regardless of prior runs.
    while gm_page.locator("#notes-body .note-del").count():
        gm_page.once("dialog", lambda d: d.accept())
        gm_page.locator("#notes-body .note-del").first.click()
        gm_page.wait_for_timeout(150)

    # Create a prep note.
    body.locator("button.note-new").click()
    body.locator(".note-title-input").fill("The Hidden Door")
    body.locator(".note-body-input").fill("Behind the tapestry, DC 15 Investigation.")
    body.locator("button.note-save").click()

    card = gm_page.locator("#notes-body .note-card")
    expect(card).to_have_count(1, timeout=3000)
    expect(card).to_contain_text("The Hidden Door")
    expect(card).to_contain_text("Behind the tapestry")

    # Edit it.
    card.locator("button.note-edit").click()
    title_input = gm_page.locator("#notes-body .note-title-input")
    expect(title_input).to_have_value("The Hidden Door")
    title_input.fill("The Secret Door")
    gm_page.locator("#notes-body button.note-save").click()
    expect(gm_page.locator("#notes-body .note-card")).to_contain_text(
        "The Secret Door", timeout=3000)

    # Delete it (accept the confirm dialog).
    gm_page.once("dialog", lambda d: d.accept())
    gm_page.locator("#notes-body .note-card button.note-del").click()
    expect(gm_page.locator("#notes-body .note-card")).to_have_count(0, timeout=3000)

    assert not errors, f"JS console errors in the Notes drawer: {errors}"
