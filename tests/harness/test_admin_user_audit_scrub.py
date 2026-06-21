"""Tests for the v2.489.0 GDPR Article 17 audit-log scrub endpoint.

``POST /admin/users/{user_id}/scrub-audit-log`` pseudonymizes a
deleted user's identifiers (``email`` + ``user_id``) in the canonical
audit log file while preserving every line + the ip/ua/event-tag the
log-based banning engines consume. See ``app/audit_scrub.py``.

Fixture pattern mirrors ``test_admin_audit.py``: create a throwaway
user via the admin portal (which emits an ``admin.user_create`` line
carrying the email into the audit log file), then scrub and assert on
the JSON summary. The audit-log file lives on the ``audit_logs``
docker volume the container owns, so the create line is on disk by the
time the scrub runs (StreamHandler flushes per emit).
"""
from __future__ import annotations

import secrets

import httpx
import pytest

from .helpers import login_client


async def _admin_client() -> httpx.AsyncClient:
    return await login_client("demo-gm@example.com", "demopass")


async def _create_throwaway_user(admin: httpx.AsyncClient) -> tuple[int, str]:
    tag = secrets.token_hex(8)
    email = f"scrub-test-{tag}@example.com"
    resp = await admin.post(
        "/admin/users",
        data={
            "email": email,
            "display_name": f"scrub-{tag}",
            "password": "test-password-12345",
        },
        follow_redirects=False,
    )
    assert resp.status_code in (303, 200), (
        f"create_user failed: {resp.status_code} {resp.text[:200]}"
    )
    # Resolve the new id from the admin user table HTML.
    import re
    page = await admin.get("/admin")
    assert page.status_code == 200
    m = re.search(
        r"<tr>\s*<td>(\d+)</td>\s*<td>" + re.escape(email), page.text,
    )
    assert m, f"could not find {email} in admin user list"
    return int(m.group(1)), email


async def test_scrub_pseudonymizes_user_and_is_idempotent():
    """Happy path: scrubbing a user whose email was just written to the
    audit log rewrites >=1 line and reports a stable ``<deleted-…>``
    pseudonym; a second scrub is a no-op (0 lines)."""
    admin = await _admin_client()
    try:
        user_id, email = await _create_throwaway_user(admin)
        # Delete so the row is gone — the scrub must work post-deletion
        # off the email captured beforehand.
        resp = await admin.post(
            f"/admin/users/{user_id}/delete", follow_redirects=False,
        )
        assert resp.status_code == 303

        resp = await admin.post(
            f"/admin/users/{user_id}/scrub-audit-log",
            data={"email": email},
            follow_redirects=False,
        )
        assert resp.status_code == 200, resp.text[:300]
        body = resp.json()
        assert body["ok"] is True
        assert body["user_id"] == user_id
        assert body["pseudonym"].startswith("<deleted-")
        # The create + delete both logged the email/id, so at least one
        # line was rewritten.
        assert body["lines_rewritten"] >= 1, body
        first_token = body["pseudonym"]

        # Idempotent: nothing left to rewrite, same stable token.
        resp = await admin.post(
            f"/admin/users/{user_id}/scrub-audit-log",
            data={"email": email},
            follow_redirects=False,
        )
        assert resp.status_code == 200, resp.text[:300]
        body2 = resp.json()
        assert body2["lines_rewritten"] == 0, body2
        assert body2["pseudonym"] == first_token
    finally:
        await admin.aclose()


async def test_scrub_missing_email_400():
    """Error path: the email field is required (it can't be looked up
    after the user row is deleted)."""
    admin = await _admin_client()
    try:
        resp = await admin.post(
            "/admin/users/99999/scrub-audit-log",
            data={},
            follow_redirects=False,
        )
        assert resp.status_code == 400, resp.text[:300]
    finally:
        await admin.aclose()


async def test_scrub_requires_admin_403():
    """Error path: a non-admin can't reach the scrub at all."""
    alice = await login_client("demo-alice@example.com", "demopass")
    try:
        resp = await alice.post(
            "/admin/users/1/scrub-audit-log",
            data={"email": "x@example.com"},
            follow_redirects=False,
        )
        assert resp.status_code == 403, resp.text[:300]
    finally:
        await alice.aclose()
