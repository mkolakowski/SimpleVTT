"""Harness tests for the HTTP security-headers middleware (v2.1035.0).

The middleware (`app/main.py::_security_headers_mw`) stamps defensive response
headers on every app response. These assert the headers the middleware sets are
actually present on a live response over HTTP, and that the CSP carries the
key restrictive directives. HSTS is intentionally NOT asserted here because the
dev/CI container runs with SESSION_COOKIE_SECURE=false (HSTS is emitted only on
an HTTPS deploy).
"""
from __future__ import annotations

import httpx

from .helpers import BASE_URL


async def test_security_headers_present_on_public_endpoint():
    """A public endpoint (/version) carries the full defensive header set."""
    async with httpx.AsyncClient(base_url=BASE_URL) as c:
        r = await c.get("/version")
    assert r.status_code == 200, r.text
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "DENY"
    assert "strict-origin" in (r.headers.get("Referrer-Policy") or "")
    assert r.headers.get("Permissions-Policy"), "Permissions-Policy missing"


async def test_content_security_policy_restrictive_directives():
    """The CSP blocks framing, plugins, and base-tag hijacking, and defaults
    to same-origin."""
    async with httpx.AsyncClient(base_url=BASE_URL) as c:
        r = await c.get("/version")
    csp = r.headers.get("Content-Security-Policy") or ""
    assert csp, "Content-Security-Policy header missing"
    for directive in (
        "default-src 'self'",
        "frame-ancestors 'none'",
        "object-src 'none'",
        "base-uri 'self'",
    ):
        assert directive in csp, f"CSP missing `{directive}`: {csp!r}"


async def test_security_headers_on_html_page():
    """Headers are stamped on HTML responses too (not just JSON) — the login
    page is the unauthenticated HTML surface."""
    async with httpx.AsyncClient(base_url=BASE_URL) as c:
        r = await c.get("/login")
    # /login renders 200 HTML on a normal or demo instance.
    assert r.status_code == 200, r.text
    assert r.headers.get("X-Frame-Options") == "DENY"
    assert r.headers.get("Content-Security-Policy")
