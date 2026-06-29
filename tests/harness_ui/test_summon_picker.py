"""v2.748.0 — summon creature-picker modal (behavior #1 of the Summon arc).

Drives the real `window.openSummonPicker` component on the tabletop: it must
fetch `/summon-options`, render the catalog creatures for the chosen CR tier,
and re-load when the summoning-option (count) changes.
"""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def _mira_id() -> int | None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        d = c.get(f"/api/campaign/{CAMPAIGN_ID}/roster").json()
        lst = d if isinstance(d, list) else d.get("characters", [])
        for ch in lst:
            if ch.get("name") == "Mira Greenleaf":
                return ch.get("id")
    return None


def test_summon_picker_opens_and_lists_creatures(gm_page: Page) -> None:
    mid = _mira_id()
    assert mid, "Mira not found"
    errors: list[str] = []
    gm_page.on("pageerror", lambda e: errors.append(str(e)))
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
    gm_page.wait_for_function(
        "() => typeof window.openSummonPicker === 'function'", timeout=8000)

    # Open the picker for Conjure Animals (defaults to the 8 × CR ¼ tier).
    gm_page.evaluate(
        """([cid]) => window.openSummonPicker({
            spell: 'conjure-animals', endpoint: 'cast_conjure_animals',
            slugField: 'beast_slug', charId: cid, slotLevel: 3,
            spellName: 'Conjure Animals' })""",
        [mid],
    )
    modal = gm_page.locator(".summon-picker-modal")
    expect(modal).to_be_visible()
    # Beast options render (CR ¼ tier has many).
    opts = gm_page.locator(".summon-picker-option")
    expect(opts.first).to_be_visible(timeout=5000)
    assert opts.count() >= 1
    # At CR ¼, a CR-1 beast must NOT be offered.
    assert gm_page.locator(".summon-picker-option", has_text="Brown Bear").count() == 0

    # Switch to the 2 × CR 1 option → the list reloads and now includes a CR-1
    # beast.
    gm_page.locator(".summon-picker-modal button", has_text="2 × CR 1").click()
    expect(
        gm_page.locator(".summon-picker-option", has_text="Brown Bear")
    ).to_be_visible(timeout=5000)

    assert not errors, f"JS errors: {errors}"
