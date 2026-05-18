"""Phase 4 smoke tests — confirm the Playwright stack can drive
the demo's character sheet without crashing."""
from playwright.sync_api import Page, expect

from .conftest import sheet_url


def test_sheet_loads_for_pip(gm_page: Page, roster: dict):
    """The standalone D&D 5e sheet for Pip renders without a
    JavaScript console error or an HTTP error status."""
    pip = roster["Pip Quickfingers"]
    console_errors = []
    gm_page.on("pageerror", lambda exc: console_errors.append(str(exc)))
    response = gm_page.goto(sheet_url(pip["id"]))
    assert response is not None and response.ok, f"Sheet load failed: {response.status if response else 'no response'}"
    # The Attacks fieldset is one of the most reliable indicators that
    # the sheet's main IIFEs ran without crashing — it's rendered by
    # the renderAttacks() function in sheet_dnd5e.html which depends
    # on the inventory + attacks data being parsed correctly.
    expect(gm_page.locator("#attacks-fieldset")).to_be_visible(timeout=3000)
    assert not console_errors, f"JS errors on sheet load: {console_errors}"


def test_sheet_loads_for_tavik(gm_page: Page, roster: dict):
    """Same smoke check for Tavik. v2.7.3 was a Tavik-Warhammer
    regression specifically; this test would have failed at the
    DOM-level if the sheet itself had broken."""
    tavik = roster["Brother Tavik Stonebrow"]
    console_errors = []
    gm_page.on("pageerror", lambda exc: console_errors.append(str(exc)))
    response = gm_page.goto(sheet_url(tavik["id"]))
    assert response is not None and response.ok
    expect(gm_page.locator("#attacks-fieldset")).to_be_visible(timeout=3000)
    # Class Resources fieldset (Channel Divinity counter etc.) is
    # specific to Tavik; verify it renders.
    expect(gm_page.locator("#resources-fieldset")).to_be_visible(timeout=3000)
    assert not console_errors, f"JS errors: {console_errors}"
