"""Capture the screenshots embedded in the player-onboarding wiki guide.

This is a **manually-run capture script**, not a pytest test (the
``capture_`` prefix keeps it out of the CI harness collection — like the
rest of ``tests/harness_ui/`` it's a local-developer tool, since the
Playwright suite isn't wired into CI). It drives the running demo app
with Chromium and writes PNGs to ``app/static/docs/onboarding/`` which
are served at ``/static/docs/onboarding/<name>.png`` and embedded by
``docs/wiki/player-onboarding.md``.

Re-run this whenever the player-facing UI changes so the guide's
screenshots stay current, then bump the guide's "Screenshots refreshed"
stamp.

Prerequisites
-------------
1. The app container is up on http://localhost:8013 with ``DEMO_MODE=true``
   (``docker compose up -d --build app``).
2. Playwright + Chromium are installed::

       pip install -r requirements-dev.txt
       playwright install chromium

Run
---
    python3 tests/harness_ui/capture_onboarding.py

Each screen is captured independently: a single failure logs a warning
and the script continues with the rest, so a flaky screen never blocks
the others. Exit status is non-zero if any screen failed.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make ``tests.harness_ui.conftest`` importable when run as a script.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from playwright.sync_api import Page, TimeoutError as PWTimeout, sync_playwright

from tests.harness_ui.conftest import (  # noqa: E402  (after sys.path tweak)
    BASE_URL,
    CAMPAIGN_ID,
    _login_get_cookie,
    disable_animations,
)

# PNGs land here; served at /static/docs/onboarding/<name>.png.
OUT_DIR = _REPO_ROOT / "app" / "static" / "docs" / "onboarding"

# Fixed viewport so reruns are byte-stable framing-wise (the demo data
# still varies run-to-run, but the crop doesn't).
VIEWPORT = {"width": 1280, "height": 800}

# Alice owns Pip Quickfingers (the Rogue) in the demo vault campaign —
# the canonical "this is your character" player view.
PLAYER_EMAIL = "demo-alice@example.com"
GM_EMAIL = "demo-gm@example.com"
DEMO_PASSWORD = "demopass"

_failures: list[str] = []


def _save(page: Page, name: str, *, full_page: bool) -> None:
    disable_animations(page)
    path = OUT_DIR / f"{name}.png"
    page.screenshot(path=str(path), full_page=full_page)
    print(f"  ✓ {name}.png")


def _wait_ready(page: Page, selector: str, timeout: int = 8000) -> None:
    """Wait for the page's key element so we never shoot a half-rendered
    frame. ``networkidle`` covers async fetches that hydrate the sheet."""
    page.wait_for_selector(selector, timeout=timeout)
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except PWTimeout:
        pass  # long-poll / WS keeps the network "busy"; the selector is enough.


def capture(name: str, fn) -> None:
    print(f"- {name}")
    try:
        fn()
    except Exception as exc:  # noqa: BLE001 — one bad screen mustn't kill the run.
        _failures.append(name)
        print(f"  ✗ {name} FAILED: {exc!r}")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Capturing onboarding screenshots → {OUT_DIR}")
    print(f"Target: {BASE_URL} (campaign {CAMPAIGN_ID})\n")

    player_cookie = _login_get_cookie(PLAYER_EMAIL, DEMO_PASSWORD)
    gm_cookie = _login_get_cookie(GM_EMAIL, DEMO_PASSWORD)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()

        # --- Logged-out screens (no cookie) -----------------------------
        anon = browser.new_context(viewport=VIEWPORT)

        capture("01-register", lambda: (
            (p := anon.new_page()),
            p.goto(f"{BASE_URL}/register"),
            _wait_ready(p, "form"),
            _save(p, "01-register", full_page=True),
            p.close(),
        ))
        capture("02-login", lambda: (
            (p := anon.new_page()),
            p.goto(f"{BASE_URL}/login"),
            _wait_ready(p, "form"),
            _save(p, "02-login", full_page=True),
            p.close(),
        ))
        anon.close()

        # --- Player screens (Alice's session) ---------------------------
        player = browser.new_context(viewport=VIEWPORT)
        player.add_cookies([player_cookie])

        capture("03-lobby", lambda: (
            (p := player.new_page()),
            p.goto(f"{BASE_URL}/"),
            _wait_ready(p, "main, .lobby, body"),
            _save(p, "03-lobby", full_page=True),
            p.close(),
        ))
        capture("04-my-characters", lambda: (
            (p := player.new_page()),
            p.goto(f"{BASE_URL}/characters"),
            _wait_ready(p, "main, body"),
            _save(p, "04-my-characters", full_page=True),
            p.close(),
        ))
        capture("05-campaign-roster", lambda: (
            (p := player.new_page()),
            p.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/characters"),
            _wait_ready(p, "main, body"),
            _save(p, "05-campaign-roster", full_page=True),
            p.close(),
        ))
        capture("06-character-sheet", lambda: (
            (p := player.new_page()),
            p.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/character/1/sheet"),
            _wait_ready(p, ".roll-btn[data-roll-ability]"),
            _save(p, "06-character-sheet", full_page=True),
            p.close(),
        ))
        capture("07-rolling-dice", _capture_roll(player))
        capture("08-roll-log", lambda: (
            (p := player.new_page()),
            p.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/rolls"),
            _wait_ready(p, "#roll-list, .roll-card, body"),
            _save(p, "08-roll-log", full_page=True),
            p.close(),
        ))
        capture("09-tabletop", lambda: (
            (p := player.new_page()),
            p.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}"),
            _wait_ready(p, "canvas, #map, .tabletop, body"),
            p.wait_for_timeout(1500),  # let the map/tokens paint onto the canvas
            _save(p, "09-tabletop", full_page=False),
            p.close(),
        ))
        capture("11-settings", lambda: (
            (p := player.new_page()),
            p.goto(f"{BASE_URL}/settings"),
            _wait_ready(p, "form, main, body"),
            _save(p, "11-settings", full_page=True),
            p.close(),
        ))
        player.close()

        # --- Monster stat block (GM-only route; captioned from the player
        #     POV — this is what a player sees when the GM reveals a
        #     monster token). Adult Red Dragon = demo template id 10. -----
        gm = browser.new_context(viewport=VIEWPORT)
        gm.add_cookies([gm_cookie])
        capture("10-monster-statblock", lambda: (
            (p := gm.new_page()),
            p.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/monster-template/10/sheet"),
            _wait_ready(p, "main, body"),
            _save(p, "10-monster-statblock", full_page=True),
            p.close(),
        ))
        gm.close()

        browser.close()

    print()
    if _failures:
        print(f"DONE with {len(_failures)} failure(s): {', '.join(_failures)}")
        return 1
    print("DONE — all screens captured.")
    return 0


def _capture_roll(context):
    """Returns a thunk that opens Pip's sheet, clicks the first ability
    roll, waits for the rich roll-toast (sheet.js POSTs /roll then calls
    window.showRollToast), and shoots the viewport with the toast up."""
    def _do() -> None:
        p = context.new_page()
        p.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/character/1/sheet")
        _wait_ready(p, ".roll-btn[data-roll-ability]")
        # Scroll the ability row into view so both the roll buttons and
        # the resulting toast share the frame.
        p.locator(".roll-btn[data-roll-ability]").first.scroll_into_view_if_needed()
        p.locator(".roll-btn[data-roll-ability]").first.click()
        p.wait_for_selector(".roll-toast", timeout=8000)
        p.wait_for_timeout(400)  # let the dice-roll animation settle
        _save(p, "07-rolling-dice", full_page=False)
        p.close()
    return _do


if __name__ == "__main__":
    raise SystemExit(main())
