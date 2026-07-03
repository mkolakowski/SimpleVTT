"""v2.783.0 — map-editor toolbar is organised into labelled sub-groups."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def test_toolbar_grouped(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
    expect(gm_page.locator("#me-overlay")).to_be_visible()

    # (CSS upper-cases the labels, so inner_text comes back upper-cased.)
    labels = [s.upper() for s in gm_page.locator(".me-group .me-grp-lbl").all_inner_texts()]
    # v2.816.0 — zoned: Actions (File · Tools) · Draw (Walls…Tokens) · Map (Grid…View).
    # v2.826.0 — History renamed "File" with Tags folded in; standalone Tags gone.
    # v2.835.0 — Props group removed (feature parked).
    # v2.870.0 — Lair group added (lair-action zones) between Environment + Tokens.
    assert labels == ["FILE", "TOOLS", "WALLS", "MARKERS", "ENVIRONMENT",
                      "LAIR", "TOKENS", "GRID", "LAYERS", "VIEW"], labels

    # v2.817.0 — two zone dividers make the Actions │ Draw │ Map zoning visible.
    zones = [s.upper() for s in gm_page.locator(".me-zone-sep .me-zone-lbl").all_inner_texts()]
    assert zones == ["DRAW", "MAP"], zones

    # v2.822.0 — the edit bar is translucent (frosted): a backdrop blur is set.
    blur = gm_page.eval_on_selector(
        ".me-toolbar",
        "el => getComputedStyle(el).backdropFilter || getComputedStyle(el).webkitBackdropFilter")
    assert "blur" in (blur or ""), blur

    # Every tool still present (grouping preserved the IDs the JS + tests use).
    for sel in ["#me-wall-btn", "#me-door-btn", "#me-wall-style", "#me-spot-btn",
                "#me-light-btn", "#me-light-type", "#me-fog-btn", "#me-token-btn",
                "#me-erase-btn", "#me-snap-btn", "#me-grid-show", "#me-ambient",
                "#me-zoom-in", "#me-zoom-fit"]:
        assert gm_page.locator(sel).count() == 1, sel
