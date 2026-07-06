"""v2.925.0 — Theme D: the Select&move tool is renamed "Grab", and a group's
caption tells you whether its controls make a NEW object or edit the
double-click-SELECTED one (docs/plans/editor-controls-reorg.md)."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID, me_clear_toolbar


def test_selmove_renamed_grab(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
    expect(gm_page.locator("#me-overlay")).to_be_visible()
    gm_page.wait_for_timeout(300)
    btn = gm_page.locator("#me-selmove-btn")
    assert "Grab" in btn.inner_text(), btn.inner_text()
    assert "Select & move" not in btn.inner_text()


def test_wall_selection_relabels_material_caption(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": [
            {"id": "w", "x1": 200, "y1": 320, "x2": 700, "y2": 320, "style": "stone"}]})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(300)
            me_clear_toolbar(gm_page)

            cap = gm_page.locator("#me-wall-cap")
            assert cap.text_content().strip() == "material"

            # Double-click the wall → the caption flips to "selected wall" (accented).
            hit = gm_page.evaluate(
                """() => {
                    const l = [...document.querySelectorAll('#me-overlay line[stroke="transparent"]')]
                        .find(l => getComputedStyle(l).pointerEvents !== 'none');
                    const r = l.getBoundingClientRect();
                    return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
                }"""
            )
            gm_page.mouse.dblclick(hit["x"], hit["y"])
            gm_page.wait_for_timeout(250)
            assert "selected wall" in cap.text_content(), cap.text_content()
            weight = gm_page.eval_on_selector("#me-wall-cap", "e => getComputedStyle(e).fontWeight")
            assert weight in ("700", "bold"), weight

            # Esc deselects → the caption reverts to "material".
            gm_page.keyboard.press("Escape")
            gm_page.wait_for_timeout(250)
            assert cap.text_content().strip() == "material", cap.text_content()
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})
