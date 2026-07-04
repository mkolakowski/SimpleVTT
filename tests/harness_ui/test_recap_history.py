"""v2.888.0 — the GM's session-recap history browser.

The "📜 Recaps" button opens a list of past recaps; clicking one shows the
(editable) nickname + GM notes and every player's note. Here we seed a recap
over HTTP, then drive the browser and assert the list row + detail view.
"""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID, tabletop_url

KEY = "harness-history-key"
NICK = "History Test Session"
GM_NOTES = "secret gm log line"


def _seed_recap() -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        r = c.put(
            f"/api/campaign/{CAMPAIGN_ID}/session-recap/{KEY}",
            json={"nickname": NICK, "gm_notes": GM_NOTES},
        )
        assert r.status_code == 200, r.text


def test_recap_history_lists_and_opens_detail(gm_page: Page) -> None:
    _seed_recap()
    gm_page.goto(tabletop_url())
    gm_page.wait_for_function(
        "() => typeof window._showRecapHistory === 'function'", timeout=8000
    )
    gm_page.evaluate("window._showRecapHistory()")

    dlg = gm_page.locator('[role="dialog"][aria-label="Session recaps"]')
    expect(dlg).to_be_visible()
    # The seeded recap shows up in the list; click it.
    row = dlg.locator("button", has_text=NICK).first
    expect(row).to_be_visible()
    row.click()

    # Detail view: the GM notes are loaded into an editable textarea.
    ta = dlg.locator("textarea")
    expect(ta).to_be_visible()
    assert GM_NOTES in ta.input_value(), ta.input_value()
    # And the player-notes section header renders (starts "Player notes (N)").
    expect(dlg.locator("text=/^Player notes \\(/")).to_be_visible()
