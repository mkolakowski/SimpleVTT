"""v2.808.0 — ambient weather: editor selector + animated tabletop overlay."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def test_editor_weather_select_persists(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.post(f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/weather", json={"weather": "none"})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(300)
            gm_page.select_option("#me-weather", "snow")
            gm_page.wait_for_timeout(300)
            assert c.get(
                f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["weather"] == "snow"
        finally:
            c.post(f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/weather", json={"weather": "none"})


def test_editor_weather_previews(gm_page: Page) -> None:
    """v2.831.0 — the editor now animates the weather on #me-weather-canvas too."""
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.post(f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/weather", json={"weather": "none"})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
            expect(gm_page.locator("#me-overlay")).to_be_visible()
            gm_page.wait_for_timeout(300)

            _has_pixels = """() => {
                const cv = document.getElementById('me-weather-canvas');
                if (!cv || !cv.width) return false;
                const d = cv.getContext('2d').getImageData(
                    0, 0, cv.width, Math.min(cv.height, 400)).data;
                for (let i = 3; i < d.length; i += 4) if (d[i] !== 0) return true;
                return false;
            }"""

            # No weather → blank canvas.
            assert gm_page.evaluate(_has_pixels) is False

            # Selecting rain draws particles in the editor itself.
            gm_page.select_option("#me-weather", "rain")
            gm_page.wait_for_timeout(400)
            assert gm_page.evaluate(_has_pixels) is True, "rain should draw in the editor"

            # Fog also renders (v2.833.0 — denser/more noticeable blobs).
            gm_page.select_option("#me-weather", "fog")
            gm_page.wait_for_timeout(400)
            assert gm_page.evaluate(_has_pixels) is True, "fog should draw in the editor"

            # Turning it off clears the canvas.
            gm_page.select_option("#me-weather", "")
            gm_page.wait_for_timeout(250)
            assert gm_page.evaluate(_has_pixels) is False, "clearing should blank it"
        finally:
            c.post(f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/weather", json={"weather": "none"})


def test_tabletop_weather_animates(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
            gm_page.wait_for_function(
                "() => typeof window._onWeatherUpdate === 'function'", timeout=8000)
            # No weather → the canvas is blank; rain → particles get drawn.
            gm_page.evaluate("() => window._onWeatherUpdate({ weather: 'rain' })")
            gm_page.wait_for_timeout(300)
            has_pixels = gm_page.evaluate("""() => {
                const cv = document.getElementById('weather-canvas');
                if (!cv) return false;
                const ctx = cv.getContext('2d');
                const d = ctx.getImageData(0, 0, cv.width, Math.min(cv.height, 400)).data;
                for (let i = 3; i < d.length; i += 4) if (d[i] !== 0) return true;
                return false;
            }""")
            assert has_pixels, "rain should draw particles on the weather canvas"
            # Turning weather off clears the canvas.
            gm_page.evaluate("() => window._onWeatherUpdate({ weather: '' })")
            gm_page.wait_for_timeout(150)
            cleared = gm_page.evaluate("""() => {
                const cv = document.getElementById('weather-canvas');
                const ctx = cv.getContext('2d');
                const d = ctx.getImageData(0, 0, cv.width, Math.min(cv.height, 400)).data;
                for (let i = 3; i < d.length; i += 4) if (d[i] !== 0) return false;
                return true;
            }""")
            assert cleared, "clearing weather should blank the canvas"
        finally:
            c.post(f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/weather", json={"weather": "none"})
