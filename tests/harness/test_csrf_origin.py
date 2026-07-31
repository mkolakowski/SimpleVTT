"""Tests for the main-app CSRF origin check (v2.1038.0).

Unit tests on the pure `_origin_matches_host` predicate + live integration
tests that a cross-origin state-changing request is rejected with 403 while a
header-less (non-browser) request is not CSRF-blocked.
"""
from __future__ import annotations

import httpx

from app.main import _origin_matches_host

from .conftest import CAMPAIGN_ID
from .helpers import BASE_URL


# ─── Unit tests on the predicate ──────────────────────────────────────


def test_matching_origin_ok():
    assert _origin_matches_host("demo.example", "https://demo.example", None) is True


def test_mismatched_origin_rejected():
    assert _origin_matches_host("demo.example", "https://evil.example", None) is False


def test_referer_used_when_origin_absent():
    assert _origin_matches_host("demo.example", None, "https://demo.example/page") is True
    assert _origin_matches_host("demo.example", None, "https://evil.example/page") is False


def test_origin_takes_precedence_over_referer():
    # First present header decides — a matching Origin wins even if Referer differs.
    assert _origin_matches_host("demo.example", "https://demo.example", "https://evil.example") is True


def test_no_headers_allowed():
    """Header-less (API/CLI/harness) requests are not CSRF-blocked."""
    assert _origin_matches_host("demo.example", None, None) is True


# ─── Live integration ─────────────────────────────────────────────────


async def test_cross_origin_post_rejected_as_csrf():
    """A POST carrying a foreign Origin is rejected with 403 before auth."""
    async with httpx.AsyncClient(base_url=BASE_URL) as c:
        r = await c.post(
            f"/api/campaign/{CAMPAIGN_ID}/background",
            headers={"origin": "http://evil.example"},
        )
    assert r.status_code == 403, r.text
    assert "csrf" in r.json()["detail"].lower()


async def test_headerless_post_not_csrf_blocked():
    """No Origin/Referer → CSRF check passes; the request proceeds to auth
    (401/redirect), NOT a CSRF 403."""
    async with httpx.AsyncClient(base_url=BASE_URL) as c:
        r = await c.post(f"/api/campaign/{CAMPAIGN_ID}/background")
    if r.status_code == 403 and r.headers.get("content-type", "").startswith("application/json"):
        assert "csrf" not in r.json().get("detail", "").lower()
