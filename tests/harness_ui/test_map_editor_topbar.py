"""v2.813.0 — the map editor's slim top bar (title + rename up top, Save in History)."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def test_editor_topbar_layout(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        am = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()
        mid, name = am["map_id"], am["name"]
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
    expect(gm_page.locator("#me-overlay")).to_be_visible()

    # The map title + rename button live in the top nav header now.
    topnav = gm_page.locator("header.topnav")
    assert topnav.locator("#me-map-name").inner_text() == name
    assert topnav.locator("#me-rename-btn").count() == 1
    # The version stamp is gone from this page's top bar.
    assert topnav.locator(".brand-version").count() == 0
    # "Back to settings" sits before Wiki in the nav.
    hrefs = gm_page.eval_on_selector_all(
        "header.topnav nav a", "els => els.map(e => e.getAttribute('href'))")
    back_i = next(i for i, h in enumerate(hrefs) if h and "settings#maps" in h)
    wiki_i = next(i for i, h in enumerate(hrefs) if h == "/wiki")
    assert back_i < wiki_i, hrefs

    # Save button lives inside the File toolbar group (renamed from History v2.826.0).
    assert gm_page.locator(
        '.me-group[aria-label="File"] #me-save-btn').count() == 1
    # The old header row is gone.
    assert gm_page.locator(".me-head").count() == 0
    # v2.827.0 — the bottom hint paragraph was removed (it duplicated tooltips).
    assert gm_page.locator(".m4hint").count() == 0
