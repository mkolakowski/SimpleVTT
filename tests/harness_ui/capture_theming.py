"""Capture the screenshots embedded in the "Theming" wiki guide.

Manually-run Playwright capture (the ``capture_`` prefix keeps it out of
CI collection). Writes PNGs to ``app/static/docs/theming/`` (served at
``/static/docs/theming/<name>.png``), embedded by
``docs/wiki/theming.md``.

The theme is an attribute (``data-theme``) on ``<html>`` — so we set it
client-side per page (``document.documentElement.setAttribute(...)``) to
shoot the *same* character sheet under different themes. This touches no
server state (no ``users.theme`` write), so it's safe on the public demo.

Prereqs: app container up on http://localhost:8013 with ``DEMO_MODE=true``;
``playwright install chromium``.

Run
---
    python3 tests/harness_ui/capture_theming.py
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

OUT_DIR = _REPO_ROOT / "app" / "static" / "docs" / "theming"
VIEWPORT = {"width": 1280, "height": 800}
PLAYER_EMAIL = "demo-alice@example.com"
DEMO_PASSWORD = "demopass"

# A representative spread across the 14 built-in themes: classic dark,
# classic light, a vibrant accent, and a fantasy theme (with a fantasy
# font) — enough to show how far the look travels.
SHEET_THEMES = [
    ("02-theme-dark", "dark", ""),
    ("03-theme-light", "light", ""),
    ("04-theme-fire", "fire", ""),
    ("05-theme-hobbiton", "hobbiton", "cormorant"),
]

_failures: list[str] = []


def _save(page: Page, name: str, *, full_page: bool = False) -> None:
    disable_animations(page)
    page.screenshot(path=str(OUT_DIR / f"{name}.png"), full_page=full_page)
    print(f"  ✓ {name}.png")


def _settle(page: Page, selector: str, timeout: int = 8000) -> None:
    page.wait_for_selector(selector, timeout=timeout)
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except PWTimeout:
        pass


def _apply(page: Page, theme: str, font: str) -> None:
    page.evaluate(
        "([t, f]) => { document.documentElement.setAttribute('data-theme', t);"
        " if (f) document.documentElement.setAttribute('data-font', f); }",
        [theme, font],
    )
    page.wait_for_timeout(250)  # let the swapped CSS variables paint


def capture(name: str, fn) -> None:
    print(f"- {name}")
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        _failures.append(name)
        print(f"  ✗ {name} FAILED: {exc!r}")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Capturing theming screenshots → {OUT_DIR}\n")
    cookie = _login_get_cookie(PLAYER_EMAIL, DEMO_PASSWORD)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport=VIEWPORT)
        ctx.add_cookies([cookie])

        # 1. The settings theme/font/display picker — the "all themes at a
        #    glance" reference.
        capture("01-theme-picker", lambda: (
            (p := ctx.new_page()),
            p.goto(f"{BASE_URL}/settings"),
            _settle(p, "form, main, body"),
            _save(p, "01-theme-picker", full_page=False),
            p.close(),
        ))

        # 2-5. The same character sheet under a spread of themes, set
        #      client-side so no server state changes.
        for name, theme, font in SHEET_THEMES:
            capture(name, lambda name=name, theme=theme, font=font: (
                (p := ctx.new_page()),
                p.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/character/1/sheet"),
                _settle(p, ".roll-btn[data-roll-ability]"),
                _apply(p, theme, font),
                _save(p, name, full_page=False),
                p.close(),
            ))

        ctx.close()
        browser.close()

    print()
    if _failures:
        print(f"DONE with {len(_failures)} failure(s): {', '.join(_failures)}")
        return 1
    print("DONE — all screens captured.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
