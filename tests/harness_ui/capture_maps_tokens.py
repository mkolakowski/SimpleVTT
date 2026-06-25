"""Capture the screenshots embedded in the "Maps, grids & tokens" guide.

Manually-run Playwright capture (the ``capture_`` prefix keeps it out of
CI collection). Writes PNGs to ``app/static/docs/maps-tokens/`` (served at
``/static/docs/maps-tokens/<name>.png``), embedded by
``docs/wiki/maps-grids-tokens.md``.

Drives the demo GM through the GM-facing map + token surfaces on the
demo "Sundered Vault" campaign (id 1), which ships a tavern battle map
with a grid + 12 tokens already placed — so the board screenshots are a
static navigate, not a multi-step placement.

Prereqs: app container up on http://localhost:8013 with ``DEMO_MODE=true``;
``playwright install chromium``.

Run
---
    python3 tests/harness_ui/capture_maps_tokens.py
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from playwright.sync_api import Page, TimeoutError as PWTimeout, sync_playwright

from tests.harness_ui.conftest import (  # noqa: E402
    BASE_URL,
    CAMPAIGN_ID,
    _login_get_cookie,
    disable_animations,
)

OUT_DIR = _REPO_ROOT / "app" / "static" / "docs" / "maps-tokens"
VIEWPORT = {"width": 1280, "height": 800}
GM_EMAIL = "demo-gm@example.com"
DEMO_PASSWORD = "demopass"

_failures: list[str] = []


def _save(page: Page, name: str, *, full_page: bool = False, locator=None) -> None:
    disable_animations(page)
    path = OUT_DIR / f"{name}.png"
    if locator is not None:
        locator.screenshot(path=str(path))
    else:
        page.screenshot(path=str(path), full_page=full_page)
    print(f"  ✓ {name}.png")


def _settle(page: Page, selector: str, timeout: int = 10000) -> None:
    page.wait_for_selector(selector, timeout=timeout)
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except PWTimeout:
        pass


def _open_tabletop(page: Page) -> None:
    """Load the tabletop, let the map paint, and make sure the GM Tools
    drawer (token management + add-token) is the active drawer."""
    page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
    _settle(page, "#vtt-canvas")
    # Activate the Tools drawer if its tab is present (defensive — it's
    # usually default).
    tab = page.locator('.drawer-tab-btn[data-target="gm-tools-drawer"]')
    if tab.count():
        try:
            tab.first.click()
        except Exception:  # noqa: BLE001
            pass
    page.wait_for_timeout(1800)  # map/token render onto the canvas


def capture(name: str, fn) -> None:
    print(f"- {name}")
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        _failures.append(name)
        print(f"  ✗ {name} FAILED: {exc!r}")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Capturing maps/tokens screenshots → {OUT_DIR}\n")
    cookie = _login_get_cookie(GM_EMAIL, DEMO_PASSWORD)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        gm = browser.new_context(viewport=VIEWPORT)
        gm.add_cookies([cookie])

        # 1. The map-management table in campaign settings → World: per-map
        #    grid-type / grid-size / show-grid toggle / Activate, + Upload.
        capture("01-maps-settings", lambda: (
            (p := gm.new_page()),
            p.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/settings"),
            _settle(p, '.settings-tab[data-tab="world"]'),
            p.locator('.settings-tab[data-tab="world"]').click(),
            p.wait_for_selector("#maps.is-shown", timeout=8000),
            _save(p, "01-maps-settings", full_page=False),
            p.close(),
        ))

        # 2. The tabletop: the active map with its grid overlay + the
        #    placed tokens.
        capture("02-tabletop-grid", lambda: (
            (p := gm.new_page()),
            _open_tabletop(p),
            _save(p, "02-tabletop-grid", full_page=False),
            p.close(),
        ))

        # 3. The token tracker (GM Tools → Token Management): the live list
        #    of every token with owner / team / HP.
        capture("03-token-tracker", lambda: (
            (p := gm.new_page()),
            _open_tabletop(p),
            p.wait_for_selector("#token-tracker-list", timeout=8000),
            _save(
                p, "03-token-tracker",
                locator=p.locator("#token-management-panel"),
            ),
            p.close(),
        ))

        # 4. The Add Token modal → Library tab: spawn a monster from a
        #    campaign token template (Adult Red Dragon, Quasit, …).
        capture("04-add-token", lambda: (
            (p := gm.new_page()),
            _open_tabletop(p),
            p.locator("#add-token-btn").click(),
            p.wait_for_selector("#add-token-modal", state="visible", timeout=6000),
            _maybe_click_library(p),
            p.wait_for_timeout(600),
            _save(p, "04-add-token", locator=p.locator("#add-token-modal")),
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


def _maybe_click_library(page: Page) -> None:
    """Make sure the Library tab (token templates) is the one showing."""
    for sel in (
        '#add-token-modal [data-atm-tab="library"]',
        '#add-token-modal button:has-text("Library")',
    ):
        loc = page.locator(sel)
        if loc.count():
            try:
                loc.first.click()
                return
            except Exception:  # noqa: BLE001
                pass


if __name__ == "__main__":
    raise SystemExit(main())
