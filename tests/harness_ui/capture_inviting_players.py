"""Capture the screenshots embedded in the "Inviting players" wiki guide.

Manually-run Playwright capture (the ``capture_`` prefix keeps it out of
CI collection — a local-developer tool like the rest of
``tests/harness_ui/``). Drives the demo app as the GM and writes PNGs to
``app/static/docs/inviting-players/`` (served at
``/static/docs/inviting-players/<name>.png``), embedded by
``docs/wiki/inviting-players.md``.

Prerequisites
-------------
1. App container up on http://localhost:8013 with ``DEMO_MODE=true``.
2. Playwright + Chromium installed (``playwright install chromium``).
3. **demo-gm must be a site admin for the "+ Add member" form to render.**
   On the public-demo box ``DEMO_GM_SITE_ADMIN=false``, so the wrapper
   ``scripts``-style invocation flips ``users.is_admin`` on for the demo
   GM around this run and reverts it afterwards. If you run this script
   directly, set demo-gm's ``is_admin`` first or the add-member shot will
   fall back to the member-table view.

Run
---
    python3 tests/harness_ui/capture_inviting_players.py
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

OUT_DIR = _REPO_ROOT / "app" / "static" / "docs" / "inviting-players"
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


def _settle(page: Page, selector: str, timeout: int = 8000) -> None:
    page.wait_for_selector(selector, timeout=timeout)
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except PWTimeout:
        pass


def capture(name: str, fn) -> None:
    print(f"- {name}")
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        _failures.append(name)
        print(f"  ✗ {name} FAILED: {exc!r}")


def _open_people_tab(page) -> None:
    """Settings page → click the People tab so the Members section shows."""
    page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/settings")
    _settle(page, '.settings-tab[data-tab="people"]')
    page.locator('.settings-tab[data-tab="people"]').click()
    page.wait_for_selector("#members.is-shown", timeout=8000)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Capturing inviting-players screenshots → {OUT_DIR}\n")
    gm_cookie = _login_get_cookie(GM_EMAIL, DEMO_PASSWORD)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        gm = browser.new_context(viewport=VIEWPORT)
        gm.add_cookies([gm_cookie])

        # 1. People tab — the members table (roll colors, Make GM, Remove,
        #    View-as-Player preview).
        capture("01-people-tab", lambda: (
            (p := gm.new_page()),
            _open_people_tab(p),
            _save(p, "01-people-tab", full_page=False),
            p.close(),
        ))

        # 2. The admin-only "+ Add member" form, expanded to show the
        #    dropdown of existing users not yet in the campaign.
        capture("02-add-member", lambda: (
            (p := gm.new_page()),
            _open_people_tab(p),
            p.locator("#members details > summary").click(),
            p.wait_for_selector('#members details form select[name="user_id"]', timeout=4000),
            _save(p, "02-add-member", full_page=False),
            p.close(),
        ))

        # 3. The campaign character roster (GM sees every PC + its owner +
        #    portrait).
        capture("03-character-roster", lambda: (
            (p := gm.new_page()),
            p.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/characters"),
            _settle(p, "main, body"),
            _save(p, "03-character-roster", full_page=False),
            p.close(),
        ))

        # 4. The portrait-upload affordance on a character sheet (the 📷
        #    label at the corner of the portrait).
        capture("04-portrait-upload", lambda: (
            (p := gm.new_page()),
            p.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/character/1/sheet"),
            _settle(p, "#char-portrait-placeholder, #char-portrait-img"),
            _save(
                p, "04-portrait-upload",
                locator=p.locator(
                    "#char-portrait-placeholder, #char-portrait-img"
                ).first.locator("xpath=ancestor::div[1]"),
            ),
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


if __name__ == "__main__":
    raise SystemExit(main())
