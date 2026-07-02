"""v2.815.0 — every toolbar dropdown carries a caption above it."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def test_every_dropdown_has_a_caption(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
    expect(gm_page.locator("#me-overlay")).to_be_visible()

    # Every <select> in the ribbon sits inside a .me-capsel label whose first
    # child is a .me-cap caption.
    captioned = gm_page.eval_on_selector_all(
        ".me-toolbar select",
        """els => els.map(sel => {
            const lab = sel.closest('label');
            const cap = lab && lab.querySelector('.me-cap');
            return !!cap && cap.textContent.trim().length > 0;
        })""")
    assert captioned and all(captioned), captioned

    # (CSS upper-cases the captions, so compare case-insensitively.)
    caps = [t.strip().lower() for t in gm_page.locator(".me-toolbar .me-capsel > .me-cap").all_inner_texts()]
    for expected in ["material", "ambient", "terrain", "weather", "grid type"]:  # v2.835.0 — prop removed
        assert expected in caps, (expected, caps)
