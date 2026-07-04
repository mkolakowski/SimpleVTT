"""v2.889.0 — the map editor's floating toolbar is compact.

The full-bleed map runs behind the toolbar, so a shorter toolbar hides less of
it. v2.889.0 laid the caption-selects out horizontally, paired the File group's
buttons, and compacted the always-expanded Layers rows — dropping the toolbar
from ~284px to ~210px at 1280×720 while keeping all 9 layer rows visible.
"""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def test_toolbar_is_compact_and_all_layers_visible(gm_page: Page) -> None:
    gm_page.set_viewport_size({"width": 1280, "height": 720})
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
    expect(gm_page.locator("#me-overlay")).to_be_visible()
    gm_page.wait_for_timeout(400)

    h = gm_page.evaluate(
        "() => Math.round(document.querySelector('.me-toolbar').getBoundingClientRect().height)"
    )
    # Comfortably below the pre-v2.889.0 ~284px (guards against a regression
    # that re-stacks the caption-selects or un-pairs the File buttons).
    assert h < 240, f"editor toolbar too tall ({h}px) — the compaction regressed"

    # All 9 layer rows stay present + visible (compaction must not hide layers).
    rows = gm_page.locator(".me-layer-row")
    assert rows.count() == 9, rows.count()
    assert rows.last.is_visible(), "the last layer row should still be visible"
