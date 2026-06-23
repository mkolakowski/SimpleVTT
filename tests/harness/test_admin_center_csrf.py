"""v2.599.8 — Admin Center CSRF origin-check (security review defense-in-depth).

`_auth_mw` rejects a state-changing request (POST/PUT/PATCH/DELETE) whose
`Origin`/`Referer` host doesn't match our `Host` — blocking the cross-origin
auto-submit a CSRF attack relies on, while leaving header-less API/harness
callers (and same-origin browser forms) untouched. Complements SameSite=Lax.

Live tests hit the unauthenticated `/users/create` route: the CSRF check runs
*before* the auth gate, so a foreign Origin → 403 CSRF, while a header-less or
same-origin POST falls through to the normal auth bounce (303), never a CSRF
403. Using a non-login route avoids the login brute-force throttle. They skip
when the service isn't reachable; a source guard always runs.
"""
from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest

ADMIN_BASE_URL = os.getenv("ADMIN_CENTER_BASE_URL", "http://localhost:8015")


def _admin_up() -> bool:
    try:
        return httpx.get(f"{ADMIN_BASE_URL}/healthz", timeout=3.0).status_code == 200
    except httpx.HTTPError:
        return False


_LIVE = pytest.mark.skipif(not _admin_up(), reason="admin-center not reachable on :8015")


def _is_csrf_403(r: httpx.Response) -> bool:
    return r.status_code == 403 and "csrf" in r.text.lower()


def test_csrf_origin_check_present_in_source():
    """Host-side guard so coverage exists even when the live stack is down."""
    src = (Path(__file__).resolve().parents[2] / "app/admin_center/main.py").read_text()
    assert "_csrf_origin_ok" in src and "_UNSAFE_METHODS" in src


@_LIVE
def test_csrf_rejects_cross_origin_post():
    r = httpx.post(
        f"{ADMIN_BASE_URL}/users/create",
        headers={"Origin": "https://evil.example.com"},
        data={}, timeout=5.0, follow_redirects=False,
    )
    assert _is_csrf_403(r), f"cross-origin POST must be CSRF-rejected; got {r.status_code}"


@_LIVE
def test_csrf_allows_header_less_post():
    # No Origin/Referer → not a browser CSRF vector → not blocked; unauth → 303.
    r = httpx.post(f"{ADMIN_BASE_URL}/users/create", data={}, timeout=5.0, follow_redirects=False)
    assert not _is_csrf_403(r), "header-less POST must not be CSRF-rejected"


@_LIVE
def test_csrf_allows_same_origin_post():
    host = httpx.get(f"{ADMIN_BASE_URL}/healthz", timeout=5.0).request.url.netloc
    r = httpx.post(
        f"{ADMIN_BASE_URL}/users/create",
        headers={"Origin": f"http://{host}"},
        data={}, timeout=5.0, follow_redirects=False,
    )
    assert not _is_csrf_403(r), "same-origin POST must pass the CSRF check"
