"""v2.158.80 — magic-items-automation Phase 2b Playwright UI test.

The HTTP harness test ``tests/harness/test_attune_item.py`` verifies
the ``/attune`` endpoint contract. This file verifies the SHEET UI
checkbox actually renders next to the equip toggle and that clicking
it fires the endpoint + updates the local state.

The v2.7.3 regression target (toast didn't render even though the
broadcast was correct) is the reason this companion exists — backend
contract green doesn't imply UI surface green.

Pip Quickfingers (Rogue Lv 7, seed: Cloak + Ring attuned) is the
canary because she's the demo PC with the most attuneable items
visible at once. We hit her sheet, scroll to the inventory, locate
the Cloak's row by name, and assert:

  - The attune checkbox `.inv-attune` is present on her Cloak row.
  - The checkbox is initially checked (seed: attuned=True).
  - Clicking it triggers the change handler → backend POST → checkbox
    flips. We verify by polling for the unchecked state.
"""
import time

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID, sheet_url


def _restore_pip_attunement(roster: dict) -> None:
    """Reset Pip's Cloak attunement back to True after a test that
    flipped it. Mirrors the HTTP-harness `restore_pip_attunement`
    fixture; the UI test doesn't share the asyncio fixture so we do
    it inline via httpx."""
    pip = roster["Pip Quickfingers"]
    with httpx.Client(base_url=BASE_URL, follow_redirects=True) as client:
        client.post(
            "/login",
            data={"email": "demo-gm@example.com", "password": "demopass"},
        )
        client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/attune",
            json={"inventory_index": 7, "attuned": True},
        )


def test_attune_checkbox_renders_and_toggles(gm_page: Page, roster: dict):
    """Pip's Cloak of Protection row in the inventory list should:

      1. Render an ``.inv-attune`` checkbox next to the equip toggle.
      2. Be checked initially (seed: attuned=True).
      3. Flip to unchecked after a click — the JS handler POSTs to
         /attune and updates local state on the 200 response.
    """
    pip = roster["Pip Quickfingers"]
    page = gm_page
    try:
        page.goto(sheet_url(pip["id"]))

        # Wait for the inventory section to be rendered. The Cloak's
        # row carries its name as visible text; we scope to its row
        # to dodge any other "Cloak" mention elsewhere on the page.
        cloak_row = page.locator(".inv-row", has_text="Cloak of Protection")
        expect(cloak_row).to_be_visible(timeout=5000)

        # The attune checkbox lives inside the row.
        attune_cb = cloak_row.locator(".inv-attune")
        expect(attune_cb).to_be_visible()
        expect(attune_cb).to_be_checked()

        # Click the checkbox → JS handler POSTs to /attune → on 200
        # the local `inventory[idx].attuned = false` + re-render. The
        # re-render swaps the checked state; we poll for it.
        attune_cb.click()

        # Re-locate after re-render (renderInventory() replaces the
        # node) and verify it's unchecked.
        deadline = time.time() + 3.0
        last_state = None
        while time.time() < deadline:
            row2 = page.locator(
                ".inv-row", has_text="Cloak of Protection",
            )
            cb2 = row2.locator(".inv-attune")
            if cb2.count() and not cb2.is_checked():
                last_state = "unchecked"
                break
            last_state = "still-checked"
            time.sleep(0.1)
        assert last_state == "unchecked", (
            f"Cloak attune checkbox did not unflip after click; "
            f"last_state={last_state}"
        )
    finally:
        _restore_pip_attunement(roster)
