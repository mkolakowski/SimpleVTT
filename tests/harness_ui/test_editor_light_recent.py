"""v2.934.0 — the flicker-colour pickers remember the last 5 colours picked;
clicking a recent swatch reuses it in the last-focused picker."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def _set_color(gm_page: Page, elid: str, hex_: str) -> None:
    gm_page.evaluate(
        """([id, v]) => { const e = document.getElementById(id); e.value = v;
            e.dispatchEvent(new Event('change', { bubbles: true })); }""",
        [elid, hex_],
    )


def test_recent_flicker_colours(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
    expect(gm_page.locator("#me-overlay")).to_be_visible()
    gm_page.wait_for_timeout(300)
    # Clear any persisted recents so the count is deterministic.
    gm_page.evaluate("() => localStorage.removeItem('me-light-recent')")
    gm_page.reload()
    expect(gm_page.locator("#me-overlay")).to_be_visible()
    gm_page.wait_for_timeout(300)

    swatches = gm_page.locator("#me-light-recent button")
    assert swatches.count() == 0

    _set_color(gm_page, "me-light-c1", "#123456")
    _set_color(gm_page, "me-light-c1", "#abcdef")
    gm_page.wait_for_timeout(100)
    # Two distinct recent swatches, newest first.
    assert swatches.count() == 2, swatches.count()

    # Focus c1, click the older swatch → c1 takes that colour.
    gm_page.evaluate("() => document.getElementById('me-light-c1').focus()")
    gm_page.locator('#me-light-recent button[title^="#123456"]').click()
    assert gm_page.eval_on_selector("#me-light-c1", "e => e.value") == "#123456"

    # Survives a reload (localStorage-backed).
    gm_page.reload()
    expect(gm_page.locator("#me-overlay")).to_be_visible()
    gm_page.wait_for_timeout(300)
    assert gm_page.locator("#me-light-recent button").count() == 2
