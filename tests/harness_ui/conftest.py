"""Pytest fixtures for the Playwright UI harness (Phase 4).

The HTTP+WS harness under ``tests/harness/`` covers backend contracts;
this directory covers UI-layer regressions that only show up when a
real browser renders the page (the canonical case: v2.7.3 weapon-
attack-toast miss, where the broadcast was correct but the toast
never appeared in the DOM).

Pattern: log in via httpx to obtain the session cookie, then seed the
cookie into the Playwright browser context. Cheaper than driving the
login form through the browser, and keeps the auth concern aligned
with the HTTP harness.
"""
from __future__ import annotations

import os
from typing import Iterator

import httpx
import pytest
from playwright.sync_api import Browser, BrowserContext, Page


BASE_URL = os.getenv("HARNESS_BASE_URL", "http://localhost:8013")
CAMPAIGN_ID = int(os.getenv("HARNESS_TEST_CAMPAIGN", "1"))


def _login_get_cookie(email: str, password: str) -> dict:
    """Run a synchronous login via httpx and pull the ``session``
    cookie out. Returns a Playwright-compatible cookie dict ready to
    feed to ``context.add_cookies([...])``.
    """
    with httpx.Client(base_url=BASE_URL, follow_redirects=True) as client:
        resp = client.post("/login", data={"email": email, "password": password})
        if resp.status_code not in (200, 303):
            raise AssertionError(f"Login failed for {email}: {resp.status_code}")
        # FastAPI's session middleware stores the session in a cookie
        # named "session" by default. Pull it out by name.
        session_cookie = client.cookies.get("session")
        if not session_cookie:
            raise AssertionError("No session cookie set after login")
        # Playwright cookie shape: {name, value, url|domain+path}.
        # The url variant is the simplest and works for any host.
        return {
            "name": "session",
            "value": session_cookie,
            "url": BASE_URL,
        }


@pytest.fixture(scope="session")
def gm_session_cookie() -> dict:
    """Logs in as the demo GM once per session and returns the cookie
    dict. Reused across all test contexts."""
    return _login_get_cookie("demo-gm@example.com", "demopass")


@pytest.fixture(scope="session")
def alice_session_cookie() -> dict:
    return _login_get_cookie("demo-alice@example.com", "demopass")


@pytest.fixture
def gm_context(browser: Browser, gm_session_cookie: dict) -> Iterator[BrowserContext]:
    """Browser context with the GM's session cookie pre-set so the
    next ``page.goto(...)`` lands on an authenticated page."""
    context = browser.new_context()
    context.add_cookies([gm_session_cookie])
    yield context
    context.close()


@pytest.fixture
def alice_context(browser: Browser, alice_session_cookie: dict) -> Iterator[BrowserContext]:
    """Browser context with Alice's session cookie."""
    context = browser.new_context()
    context.add_cookies([alice_session_cookie])
    yield context
    context.close()


@pytest.fixture
def gm_page(gm_context: BrowserContext) -> Iterator[Page]:
    """Fresh authenticated page in the GM context. Each test gets a
    new page so dialog/modal/leftover-DOM state from a prior test
    can't poison the next."""
    page = gm_context.new_page()
    yield page
    page.close()


@pytest.fixture
def alice_page(alice_context: BrowserContext) -> Iterator[Page]:
    page = alice_context.new_page()
    yield page
    page.close()


@pytest.fixture(scope="session")
def roster() -> dict:
    """Same lookup as the HTTP harness: map character names →
    {id, hp_current, hp_max, ...}. Used so tests reference characters
    by name + don't hardcode IDs."""
    with httpx.Client(base_url=BASE_URL, follow_redirects=True) as client:
        client.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        resp = client.get(f"/api/campaign/{CAMPAIGN_ID}/roster")
        assert resp.status_code == 200, resp.text
        chars = resp.json()["characters"]
        return {c["name"]: c for c in chars}


def me_clear_toolbar(page, gap: int = 24) -> None:
    """v2.883.0 — the map editor is now full-bleed: the map fills the whole
    stage and the floating toolbar overlays its top ~280px (the always-expanded
    vertical Layers panel is tall). So map content near the top renders BEHIND
    the toolbar, where clicks hit toolbar buttons instead of the map. Tests call
    this after opening the editor to pan the map down until the overlay's top
    clears the toolbar's bottom edge, exactly as a GM would drag the map out from
    under the ribbon before drawing there."""
    page.wait_for_function("() => typeof window.__editorPanBy === 'function'", timeout=8000)
    geo = page.evaluate(
        """() => {
            const tb = document.querySelector('.me-toolbar').getBoundingClientRect();
            const ov = document.getElementById('me-overlay').getBoundingClientRect();
            return { tbBottom: tb.bottom, ovTop: ov.y };
        }"""
    )
    dy = (geo["tbBottom"] + gap) - geo["ovTop"]
    if dy > 0:
        page.evaluate("(dy) => window.__editorPanBy(0, dy)", dy)
        page.wait_for_timeout(60)


def sheet_url(char_id: int) -> str:
    """URL helper for the standalone character-sheet page."""
    return f"{BASE_URL}/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet"


def tabletop_url() -> str:
    """URL helper for the campaign tabletop page (the campaign page IS
    the tabletop view — there's no ``/tabletop`` suffix)."""
    return f"{BASE_URL}/campaign/{CAMPAIGN_ID}"


# v2.97.13 — Visual regression infrastructure.
#
# Pillow-based screenshot diff. The Python Playwright sync API doesn't
# ship the JS `to_have_screenshot()` assertion, so we roll our own
# minimal version: take a screenshot of a Locator (or the whole page)
# into __snapshots__/<test-name>.png; on first run write the file as a
# baseline, on subsequent runs compare via ImageChops + pixel-diff
# threshold. Baselines are committed; intentional visual changes get
# updated by re-running with `--update-snapshots`.
#
# Cross-machine determinism caveat: snapshots are sensitive to font
# rendering / anti-aliasing / OS. For now this is a local-developer
# tool — CI integration is intentionally deferred so we don't fail on
# Mac-vs-Linux pixel jitter. When CI integration is wanted, the right
# move is to bake snapshots inside a Linux Docker stage and run the
# diff there.
import shutil
from pathlib import Path

from playwright.sync_api import Locator, Page


SNAPSHOT_DIR = Path(__file__).parent / "__snapshots__"


def pytest_addoption(parser):
    parser.addoption(
        "--update-snapshots",
        action="store_true",
        default=False,
        help="Update visual-regression baselines instead of comparing.",
    )


@pytest.fixture
def update_snapshots(request) -> bool:
    return bool(request.config.getoption("--update-snapshots"))


# Stylesheet injected into the page before snapshot capture so CSS
# transitions / animations don't introduce frame-timing flake.
_DISABLE_ANIMATIONS_CSS = """
* { transition: none !important; animation: none !important; }
*::before, *::after { transition: none !important; animation: none !important; }
"""


def disable_animations(page: Page) -> None:
    """Inject a stylesheet that nukes CSS transitions + animations.
    Call after page load (and after any expanding details have been
    clicked into their final state) before taking a screenshot."""
    page.add_style_tag(content=_DISABLE_ANIMATIONS_CSS)


def assert_visual_match(
    locator: Locator,
    name: str,
    *,
    update: bool = False,
    max_diff_fraction: float = 0.01,
) -> None:
    """Take a screenshot of the locator and compare it to the baseline
    at ``__snapshots__/<name>.png``.

    Workflow:
      - If the baseline doesn't exist OR ``update`` is True, write the
        current screenshot as the new baseline. (First-run capture.)
      - Otherwise compare via Pillow ImageChops bbox + pixel count;
        fail if the fraction of differing pixels exceeds
        ``max_diff_fraction``.

    ``name`` should be unique across the suite; conventionally
    ``<test-file>__<test-fn>__<state>``.
    """
    from PIL import Image, ImageChops

    SNAPSHOT_DIR.mkdir(exist_ok=True)
    baseline_path = SNAPSHOT_DIR / f"{name}.png"
    current_path = SNAPSHOT_DIR / f"{name}.current.png"

    locator.screenshot(path=str(current_path))

    if update or not baseline_path.exists():
        # First-run capture (or explicit update) — promote current to baseline.
        shutil.copyfile(current_path, baseline_path)
        current_path.unlink(missing_ok=True)
        return

    with Image.open(baseline_path) as base_img, Image.open(current_path) as cur_img:
        if base_img.size != cur_img.size:
            raise AssertionError(
                f"Visual diff: size mismatch for {name!r}. "
                f"Baseline={base_img.size}, current={cur_img.size}. "
                f"See {current_path} vs {baseline_path}."
            )
        diff = ImageChops.difference(base_img.convert("RGB"), cur_img.convert("RGB"))
        bbox = diff.getbbox()
        if bbox is None:
            current_path.unlink(missing_ok=True)
            return
        # Count diffing pixels (any channel non-zero).
        diff_data = diff.getdata()
        diff_count = sum(1 for px in diff_data if px != (0, 0, 0))
        total = base_img.size[0] * base_img.size[1]
        fraction = diff_count / total if total else 0
        if fraction > max_diff_fraction:
            raise AssertionError(
                f"Visual diff for {name!r}: {diff_count}/{total} pixels "
                f"({fraction:.2%}) exceed max_diff_fraction "
                f"({max_diff_fraction:.2%}). "
                f"See {current_path} vs {baseline_path}. "
                f"Re-run with --update-snapshots after confirming the "
                f"intentional change."
            )
        current_path.unlink(missing_ok=True)
