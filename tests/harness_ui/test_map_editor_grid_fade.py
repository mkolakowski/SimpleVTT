"""v2.786.3 — the editor grid fades as the ambient light drops."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID

_GRID_ALPHA = """() => {
    const lines = [...document.querySelectorAll('#me-overlay line')];
    const g = lines.find(l => (l.getAttribute('stroke') || '').indexOf('rgba(255,255,255,') === 0);
    if (!g) return null;
    const m = g.getAttribute('stroke').match(/,([\\d.]+)\\)$/);
    return m ? parseFloat(m[1]) : null;
}"""


def test_grid_fades_with_ambient(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})  # only grid lines
        c.post(f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/show_grid", json={"show_grid": True})
        c.post(f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/ambient_light", json={"ambient_light": "bright"})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(400)
            bright = gm_page.evaluate(_GRID_ALPHA)
            assert bright is not None and bright > 0.15, bright
            # Dim the ambient → grid gets fainter.
            gm_page.select_option("#me-ambient", "dark")
            gm_page.wait_for_timeout(300)
            dark = gm_page.evaluate(_GRID_ALPHA)
            assert dark is not None and dark < bright, (bright, dark)
        finally:
            c.post(f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/ambient_light", json={"ambient_light": "bright"})
