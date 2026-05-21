"""Pytest fixtures for the encounter-simulation suite.

See ``docs/plans/encounter-sim-test-suite.md`` for the full plan.

Pattern is the same as ``tests/harness_ui/conftest.py`` — log in via
httpx to obtain a session cookie, then seed it into Playwright. The
two suites are siblings: ``harness_ui`` covers smoke-level UI checks
(does the toast appear?), ``encounter_sim`` covers full end-to-end
encounter playthroughs with multi-layer assertions (HTTP + WS + DOM
+ canvas).

Re-uses ``harness_ui.conftest._login_get_cookie`` rather than
duplicating the login path so the two suites can't drift on auth.
"""
from __future__ import annotations

import os
from typing import Iterator

import httpx
import pytest
from playwright.sync_api import Browser, BrowserContext, Page

# Reach across to harness_ui's login helper so there's one source of
# truth for "log in as demo user + return Playwright cookie dict".
from ..harness_ui.conftest import _login_get_cookie  # noqa: F401


BASE_URL = os.getenv("HARNESS_BASE_URL", "http://localhost:8013")
CAMPAIGN_ID = int(os.getenv("HARNESS_TEST_CAMPAIGN", "1"))


@pytest.fixture(scope="session")
def gm_session_cookie() -> dict:
    """Session-scoped: log in as the demo GM once, reuse the cookie
    across every test context in the run."""
    return _login_get_cookie("demo-gm@example.com", "demopass")


@pytest.fixture
def gm_context(browser: Browser, gm_session_cookie: dict) -> Iterator[BrowserContext]:
    """Browser context with the GM cookie pre-set so ``page.goto(...)``
    lands on an authenticated page directly."""
    context = browser.new_context()
    context.add_cookies([gm_session_cookie])
    yield context
    context.close()


@pytest.fixture
def gm_page(gm_context: BrowserContext) -> Iterator[Page]:
    """Fresh authenticated page in the GM context per test — DOM /
    dialog / modal state from prior tests can't poison the next."""
    page = gm_context.new_page()
    yield page
    page.close()


@pytest.fixture(scope="session")
def alice_session_cookie() -> dict:
    """v2.49.35: Alice (demo player owning Pip Quickfingers) session
    cookie. Used by player-driver tests that need a non-GM viewpoint —
    layer-6 init-tracker HP DOM assertions, multi-user concurrency
    scenarios, strict-mode gate validation.
    """
    return _login_get_cookie("demo-alice@example.com", "demopass")


@pytest.fixture
def alice_context(browser: Browser, alice_session_cookie: dict) -> Iterator[BrowserContext]:
    """Browser context pre-authenticated as Alice. Same shape as
    ``gm_context`` — page.goto lands on the authenticated view.
    """
    context = browser.new_context()
    context.add_cookies([alice_session_cookie])
    yield context
    context.close()


@pytest.fixture
def alice_page(alice_context: BrowserContext) -> Iterator[Page]:
    page = alice_context.new_page()
    yield page
    page.close()


@pytest.fixture(scope="session")
def roster() -> dict:
    """Map character name → roster row dict (id, hp_current, hp_max, …).
    Test code looks up by name so it survives the demo's autoincrement
    IDs changing across resets.
    """
    with httpx.Client(base_url=BASE_URL, follow_redirects=True) as client:
        client.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        resp = client.get(f"/api/campaign/{CAMPAIGN_ID}/roster")
        assert resp.status_code == 200, resp.text
        chars = resp.json()["characters"]
        return {c["name"]: c for c in chars}


@pytest.fixture
def set_dice_seed():
    """Function-scoped helper that POSTs to ``/api/test/dice/seed``
    (TEST_MODE-only endpoint, v2.49.12) to re-seed the shared dice
    RNG. Pass an int for determinism, ``None`` to return to OS entropy.

    On teardown the fixture re-seeds with ``None`` so the RNG goes
    back to OS entropy. Without this, a seeded encounter-sim test
    would leave the SHARED process-global RNG in a deterministic state
    — any subsequent test (encounter-sim, harness, or harness-ui
    sharing the same container) would observe predictable rolls and
    flake assertions that expect statistical variation. See the
    "DICE_SEED env var leaks into production" risk in the plan's
    Risks & Mitigations table.

    Usage:
        def test_x(set_dice_seed, gm_page, roster):
            set_dice_seed(42)
            # all subsequent rolls deterministic
    """
    from .helpers.dice import set_dice_seed as _set_dice_seed
    yield _set_dice_seed
    # Reset the shared RNG so the next test starts from OS entropy.
    try:
        _set_dice_seed(None)
    except Exception:
        # Don't fail teardown if the stack is unreachable — the test
        # itself would have already failed louder.
        pass


def sheet_url(char_id: int) -> str:
    """URL helper for the standalone character-sheet page."""
    return f"{BASE_URL}/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet"


def tabletop_url() -> str:
    """URL helper for the campaign's tabletop page."""
    return f"{BASE_URL}/campaign/{CAMPAIGN_ID}"
