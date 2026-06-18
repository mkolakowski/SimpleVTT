"""Integration tests for the v2.426.0 API-surface audit emission.

The global ``_auth_redirect_handler`` in ``app/main.py`` now emits
canonical audit-log lines for protected-endpoint 401/403 responses.
The legitimate browser-bounce path (HTML request to a guarded page
that gets redirected to ``/login``) is explicitly excluded so the
log doesn't drown in normal browser navigation noise.

These tests exercise the contract from the outside — they don't
verify the audit emission directly (that's covered by
``test_audit_log.py``), they verify the **response codes** that
trigger the emission. The audit module's unit tests prove that any
event with the right inputs emits the right line shape.
"""
from __future__ import annotations

import httpx
import pytest

from .helpers import BASE_URL, login_client


async def test_anonymous_api_request_to_protected_endpoint_returns_401():
    """A request with ``Accept: application/json`` to a protected
    endpoint should land 401 (not redirect). The global handler
    then emits ``api.unauthorized`` for the audit log — fail2ban
    treats this as a credential-probe signal.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0, follow_redirects=False) as client:
        # /admin requires admin auth — hitting it anon → 401.
        resp = await client.get("/admin", headers={"Accept": "application/json"})
    assert resp.status_code == 401


async def test_anonymous_html_browser_bounce_is_redirect_not_401():
    """The negative case: an unauthenticated HTML browser request to
    a protected page should get the v2.3.28 303 redirect to
    ``/login?next=…``. The audit emit is SKIPPED on this path — it
    fires every time a normal user clicks a guarded link, so
    logging it would drown the real probe signals.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0, follow_redirects=False) as client:
        resp = await client.get("/admin", headers={"Accept": "text/html"})
    assert resp.status_code == 303
    assert "/login?next=" in resp.headers.get("location", "")


async def test_non_admin_user_hitting_admin_endpoint_returns_403():
    """A logged-in non-admin user (demo-alice) hitting ``/admin``
    raises ``HTTPException(403)``. The global handler emits
    ``api.forbidden`` so the operator can spot a user trying to
    escalate privileges or probe admin paths.
    """
    client = await login_client("demo-alice@example.com", "demopass")
    try:
        resp = await client.get("/admin", follow_redirects=False)
    finally:
        await client.aclose()
    assert resp.status_code == 403
