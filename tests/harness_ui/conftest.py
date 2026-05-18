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


def sheet_url(char_id: int) -> str:
    """URL helper for the standalone character-sheet page."""
    return f"{BASE_URL}/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet"
