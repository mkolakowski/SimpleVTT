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

    Usage:
        def test_x(set_dice_seed, gm_page, roster):
            set_dice_seed(42)
            # all subsequent rolls deterministic
    """
    from .helpers.dice import set_dice_seed as _set_dice_seed
    return _set_dice_seed


def sheet_url(char_id: int) -> str:
    """URL helper for the standalone character-sheet page."""
    return f"{BASE_URL}/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet"


def tabletop_url() -> str:
    """URL helper for the campaign's tabletop page."""
    return f"{BASE_URL}/campaign/{CAMPAIGN_ID}"
