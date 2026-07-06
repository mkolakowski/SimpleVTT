"""v2.935.1 — the Bright/Dim light labels read "B [field] D [field]" inline (the
global `label { flex-direction:column }` used to stack the letter above the
field); the stacked caption variant (material) stays caption-above-control."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def test_light_bd_labels_are_inline(gm_page: Page) -> None:
    gm_page.set_viewport_size({"width": 1800, "height": 1000})
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
    expect(gm_page.locator("#me-overlay")).to_be_visible()
    gm_page.wait_for_timeout(400)

    r = gm_page.evaluate(
        """() => {
            const bl = document.getElementById('me-light-bright').closest('label');
            const rb = bl.getBoundingClientRect();
            const bi = document.getElementById('me-light-bright').getBoundingClientRect();
            const matcap = document.getElementById('me-wall-cap').closest('label');
            return {
                dir: getComputedStyle(bl).flexDirection,
                one_row: Math.round(rb.height) <= 36,
                input_right_of_letter: bi.x > rb.x + 4,
                input_same_row: Math.abs(bi.y - rb.y) < 12,
                mat_dir: getComputedStyle(matcap).flexDirection,
            };
        }"""
    )
    assert r["dir"] == "row", r          # B [field], not B over field
    assert r["one_row"], r
    assert r["input_right_of_letter"], r
    assert r["input_same_row"], r
    # The stacked caption variant is unaffected (caption still above its control).
    assert r["mat_dir"] == "column", r
