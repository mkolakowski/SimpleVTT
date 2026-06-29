"""v2.742.0 — point-buy ability-score calculator (sheet edit view).

Drives the real client widget: open the abilities edit view, click 📊 Point
buy (resets all six to 8 → 27/27 remaining), then verify the live budget
updates as scores change and over-15 entries clamp.
"""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def _pip_id() -> int | None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        d = c.get(f"/api/campaign/{CAMPAIGN_ID}/roster").json()
        lst = d if isinstance(d, list) else d.get("characters", [])
        for ch in lst:
            if ch.get("name") == "Pip Quickfingers":
                return ch.get("id")
    return None


def test_pointbuy_budget_and_clamp(gm_page: Page) -> None:
    pid = _pip_id()
    assert pid, "Pip not found in roster"
    errors: list[str] = []
    gm_page.on("pageerror", lambda e: errors.append(str(e)))
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/character/{pid}/sheet")

    # Reveal the abilities edit view, then enter point-buy mode.
    gm_page.click("#ab-edit-btn")
    expect(gm_page.locator("#ab-pointbuy-btn")).to_be_visible()
    gm_page.click("#ab-pointbuy-btn")

    budget = gm_page.locator("#ab-pb-budget")
    expect(budget).to_be_visible()
    # All six reset to 8 → full 27 budget remaining.
    expect(budget).to_contain_text("27 / 27")
    assert gm_page.input_value("#ab-input-STR") == "8"

    # Raise STR to 15 (cost 9) → 18 remaining.
    gm_page.fill("#ab-input-STR", "15")
    gm_page.dispatch_event("#ab-input-STR", "input")
    expect(budget).to_contain_text("18 / 27")

    # Over-15 entry clamps back to 15 (point-buy ceiling).
    gm_page.fill("#ab-input-DEX", "30")
    gm_page.dispatch_event("#ab-input-DEX", "input")
    assert gm_page.input_value("#ab-input-DEX") == "15"

    assert not errors, f"JS errors on the sheet: {errors}"
