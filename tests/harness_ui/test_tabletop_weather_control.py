"""v2.809.0 — live GM weather control on the tabletop."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page

from .conftest import BASE_URL, CAMPAIGN_ID


def test_gm_live_weather_button(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.post(f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/weather", json={"weather": "none"})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
            gm_page.wait_for_function(
                "() => typeof window.setLiveWeather === 'function'", timeout=8000)
            # Click the Rain button → the active map's weather is set server-side.
            gm_page.eval_on_selector("#live-weather-btns button[data-wx='rain']", "b => b.click()")
            gm_page.wait_for_timeout(400)
            assert c.get(
                f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["weather"] == "rain"
            # The Rain button reflects the active state.
            assert gm_page.eval_on_selector(
                "#live-weather-btns button[data-wx='rain']",
                "b => b.classList.contains('active')") is True
        finally:
            c.post(f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/weather", json={"weather": "none"})
