"""Capture the screenshots embedded in the "Building an encounter" guide.

Manually-run Playwright capture (the ``capture_`` prefix keeps it out of
CI collection). Writes PNGs to ``app/static/docs/encounters/`` (served at
``/static/docs/encounters/<name>.png``), embedded by
``docs/wiki/building-an-encounter.md``.

Drives the demo GM through the encounter-building surfaces on the demo
"Sundered Vault" campaign (id 1), which ships the "Tavern Brawl"
encounter + a roster of monster token templates — so the library /
roster screenshots are a static navigate.

Prereqs: app container up on http://localhost:8013 with ``DEMO_MODE=true``;
``playwright install chromium``.

Run
---
    python3 tests/harness_ui/capture_encounters.py
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

OUT_DIR = _REPO_ROOT / "app" / "static" / "docs" / "encounters"
VIEWPORT = {"width": 1280, "height": 900}
GM_EMAIL = "demo-gm@example.com"
DEMO_PASSWORD = "demopass"

_failures: list[str] = []


def _save(page: Page, name: str, *, locator=None, full_page: bool = False) -> None:
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


def _world_tab(page: Page) -> None:
    page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/settings")
    _settle(page, '.settings-tab[data-tab="world"]')
    page.locator('.settings-tab[data-tab="world"]').click()
    page.wait_for_selector("#encounters.is-shown", timeout=8000)


def capture(name: str, fn) -> None:
    print(f"- {name}")
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        _failures.append(name)
        print(f"  ✗ {name} FAILED: {exc!r}")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Capturing encounter screenshots → {OUT_DIR}\n")
    cookie = _login_get_cookie(GM_EMAIL, DEMO_PASSWORD)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        gm = browser.new_context(viewport=VIEWPORT)
        gm.add_cookies([cookie])

        # 1. The encounter library (Settings → World → Encounters): the
        #    saved "Tavern Brawl" encounter + search / + New Encounter.
        capture("01-encounter-library", lambda: (
            (p := gm.new_page()),
            _world_tab(p),
            p.locator("#encounters").scroll_into_view_if_needed(),
            p.wait_for_selector("#encounters .enc-card", state="attached", timeout=8000),
            # The library groups encounters under collapsible folders; expand
            # the demo folder so the Tavern Brawl card itself shows.
            p.get_by_text("DEMO (1)").first.click(),
            p.wait_for_timeout(800),
            _save(p, "01-encounter-library", locator=p.locator("#encounters")),
            p.close(),
        ))

        # 2. The token-template roster — the monsters/NPCs an encounter
        #    draws from (Adult Red Dragon, bandits, …).
        capture("02-token-templates", lambda: (
            (p := gm.new_page()),
            _world_tab(p),
            p.wait_for_selector("#tmpl .tmpl-card", timeout=8000),
            p.locator("#tmpl").scroll_into_view_if_needed(),
            _save(p, "02-token-templates", locator=p.locator("#tmpl")),
            p.close(),
        ))

        # 3. The SRD/Open5e bestiary search — add a monster as a new
        #    template by searching the 5e bestiary.
        capture("03-bestiary-search", lambda: (
            (p := gm.new_page()),
            _world_tab(p),
            p.wait_for_selector("#o5e-search-btn", timeout=8000),
            p.locator("#o5e-search-btn").scroll_into_view_if_needed(),
            p.locator("#o5e-search-btn").click(),
            p.wait_for_selector("#o5e-panel", state="visible", timeout=6000),
            p.locator("#o5e-query").fill("goblin"),
            p.locator("#o5e-query").press("Enter"),
            p.wait_for_selector("#o5e-results > *", timeout=8000),
            p.wait_for_timeout(500),
            _save(p, "03-bestiary-search", locator=p.locator("#o5e-panel")),
            p.close(),
        ))

        # 4. The "Encounter on session start" default-encounter wiring
        #    (Settings → Basic info).
        capture("04-default-encounter", lambda: (
            (p := gm.new_page()),
            p.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/settings"),
            _settle(p, 'select[name="default_encounter_id"]'),
            p.locator('select[name="default_encounter_id"]').scroll_into_view_if_needed(),
            _save(
                p, "04-default-encounter",
                locator=p.locator('select[name="default_encounter_id"]').locator(
                    "xpath=ancestor::fieldset[1]"
                ),
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
