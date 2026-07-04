"""v2.884.0 — the login screen lists the FULL demo cast + a campaigns toggle.

Under DEMO_MODE the /login page's demo box is built from a server-side roster
(``_demo_login_roster``) rather than a hardcoded 3-account list: every seeded
demo account appears with a Fill button, and a "Show campaigns" toggle reveals
which campaigns each account belongs to (GM / Co-GM / Player).
"""
from __future__ import annotations

import httpx
import pytest

BASE_URL = "http://localhost:8013"

# The full seeded demo cast (app/demo_seed.py:DEMO_EMAILS). All share "demopass".
DEMO_EMAILS = [
    "demo-gm@example.com",
    "demo-alice@example.com",
    "demo-bob@example.com",
    "demo-gm2@example.com",
    "demo-carol@example.com",
    "demo-dave@example.com",
    "demo-erin@example.com",
]


@pytest.mark.asyncio
async def test_login_lists_full_demo_cast_and_campaign_toggle():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as c:
        r = await c.get("/login")
    assert r.status_code == 200, r.status_code
    body = r.text

    # If the deployment isn't in demo mode there's no roster to assert on;
    # the box is gated on DEMO_MODE. Skip rather than fail in that case.
    if "demo-creds-box" not in body:
        pytest.skip("login page not in demo mode (no demo-creds box)")

    # Every seeded demo account is offered (not just the old hardcoded three).
    for email in DEMO_EMAILS:
        assert email in body, f"missing demo account on login page: {email}"
    # Each account carries a Fill button.
    assert body.count('class="demo-fill-btn"') == len(DEMO_EMAILS), body.count('class="demo-fill-btn"')

    # The campaigns toggle exists…
    assert 'id="demo-show-campaigns"' in body, "missing Show-campaigns toggle"
    # …and per-account campaign lists are rendered (hidden until toggled).
    assert 'class="demo-campaigns"' in body, "missing per-account campaign lists"
    # A known demo campaign + at least one role label show through the roster.
    assert "Sundered Vault" in body, "expected a seeded campaign name in the roster"
    assert "Player" in body and "GM" in body, "expected role labels in the roster"


@pytest.mark.asyncio
async def test_login_demo_campaign_lists_hidden_by_default():
    """The campaign sub-lists are ``hidden`` until the toggle is checked."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as c:
        r = await c.get("/login")
    assert r.status_code == 200
    body = r.text
    if "demo-creds-box" not in body:
        pytest.skip("login page not in demo mode")
    # Every campaign list is rendered with the `hidden` attribute (collapsed).
    assert 'class="demo-campaigns" hidden' in body, "campaign lists should start hidden"
