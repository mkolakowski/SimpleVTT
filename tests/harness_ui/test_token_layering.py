"""v2.861.0 — tokens are the top-most layer and stay legible when zoomed out.

Two guards for "The Raised Piece":
  * Layering — tokens (and the gameplay markers) draw on ``#token-veil-canvas``,
    which sits ABOVE the map decoration (``#wall-overlay`` / ``#light-glow-canvas``
    z-3, ``#weather-canvas`` z-4) so terrain/walls no longer paint over tokens.
    The veil canvas is ``pointer-events:none`` so token drag + door clicks still
    fall through. The canvas actually carries drawn pixels (tokens render there).
  * Min on-screen size — the token radius is floored to ``TOKEN_MIN_SCREEN_PX``
    on screen, so a size-1 token stays legible when the camera is zoomed out on a
    large natural-res map.
"""
from __future__ import annotations

from playwright.sync_api import Page

from .conftest import BASE_URL, CAMPAIGN_ID


def test_token_veil_is_above_decoration_and_click_transparent(gm_page: Page) -> None:
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
    gm_page.wait_for_selector("#token-veil-canvas", timeout=8000)
    gm_page.wait_for_timeout(600)

    r = gm_page.evaluate(
        """() => {
            const z = (id) => parseInt(getComputedStyle(document.getElementById(id)).zIndex || '0', 10);
            const veil = document.getElementById('token-veil-canvas');
            // Any non-transparent pixel proves tokens/markers paint on the veil.
            const ctx = veil.getContext('2d');
            const d = ctx.getImageData(0, 0, veil.width, veil.height).data;
            let painted = 0;
            for (let i = 3; i < d.length; i += 4) { if (d[i] > 0) { painted++; if (painted > 50) break; } }
            return {
                veilZ: z('token-veil-canvas'),
                wallZ: z('wall-overlay'),
                glowZ: z('light-glow-canvas'),
                weatherZ: z('weather-canvas'),
                pointerEvents: getComputedStyle(veil).pointerEvents,
                painted,
            };
        }"""
    )
    # Tokens (on the veil) sit above every decoration layer.
    assert r["veilZ"] > r["wallZ"], r
    assert r["veilZ"] > r["glowZ"], r
    assert r["veilZ"] > r["weatherZ"], r
    # Clicks fall through to the interactive layers below (drag / doors).
    assert r["pointerEvents"] == "none", r
    # Tokens actually render on the veil canvas.
    assert r["painted"] > 0, f"expected drawn token pixels on the veil canvas: {r}"


def test_token_radius_floored_to_min_screen_size_when_zoomed_out(gm_page: Page) -> None:
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
    gm_page.wait_for_function(
        "() => window.__tokenRadiusForTest && window.__camScaleForTest", timeout=8000
    )
    gm_page.wait_for_timeout(400)

    r = gm_page.evaluate(
        """() => {
            const scale = window.__camScaleForTest();
            const rad = window.__tokenRadiusForTest({ size: 1 });
            return { scale, screenDiameter: rad * scale * 2, floor: window.__tokenMinScreenPx * 2 };
        }"""
    )
    # A size-1 token never renders below the on-screen floor (~52px diameter),
    # even when the camera has scaled the large map down to fit the viewport.
    assert r["screenDiameter"] >= r["floor"] - 1, r
