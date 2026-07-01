"""v2.804.0 — public text labels render on the tabletop."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page

from .conftest import BASE_URL, CAMPAIGN_ID


def test_tabletop_renders_labels(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/labels", json={"labels": [
            {"x": 120, "y": 130, "text": "The Vault", "size": 30, "color": "#ffd23a"}]})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
            gm_page.wait_for_function(
                "() => typeof window._onLabelsUpdate === 'function'", timeout=8000)
            gm_page.evaluate("""() => window._onLabelsUpdate({ labels: [
                { id: 'lb', x: 120, y: 130, text: 'The Vault', size: 30, color: '#ffd23a' }] })""")
            gm_page.wait_for_timeout(200)
            texts = gm_page.eval_on_selector_all(
                "#wall-overlay text.tt-label",
                "els => els.map(e => e.textContent)")
            assert "The Vault" in texts, texts
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/labels", json={"labels": []})
