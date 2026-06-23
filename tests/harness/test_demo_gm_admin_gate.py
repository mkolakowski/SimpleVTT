"""Demo-account site-admin role contract (v2.495.0).

The demo GM (demo-gm@example.com) is granted SITE-admin — the
``/admin`` portal (user management, audit-log scrub, ban controls) —
only when ``DEMO_GM_SITE_ADMIN`` is on. The flag defaults ON, which is
what local/CI run with, so these tests assert the default contract:

  - demo-gm reaches ``GET /admin`` (200) — it's a site-admin.
  - demo-alice / demo-bob get 403 — players are never admin,
    regardless of the flag.

The OFF branch (public-deploy hardening: demo-gm loses ``/admin``) is
config-only — flipping ``DEMO_GM_SITE_ADMIN=false`` + a reseed — and
isn't exercised here because the suite runs against a single
default-config container. The point of these tests is to lock in that
(a) the players are NEVER admin and (b) the GM's admin access is a
real, testable surface that the flag governs.

See ``app/demo_seed.py::_demo_gm_site_admin``.
"""
from __future__ import annotations

import httpx

from .helpers import login_client


async def _client(email: str) -> httpx.AsyncClient:
    return await login_client(email, "demopass")


async def test_demo_gm_reaches_admin_portal():
    """demo-gm is site-admin by default → GET /admin returns 200."""
    client = await _client("demo-gm@example.com")
    try:
        resp = await client.get("/admin")
        assert resp.status_code == 200, resp.text
        # The admin home renders the user-management table; a cheap
        # substring check confirms we got the portal, not a bounce.
        assert "admin" in resp.text.lower()
    finally:
        await client.aclose()


async def test_demo_alice_denied_admin_portal():
    """demo-alice is a player → GET /admin is forbidden (403)."""
    client = await _client("demo-alice@example.com")
    try:
        resp = await client.get("/admin")
        assert resp.status_code == 403, resp.text
    finally:
        await client.aclose()


async def test_demo_bob_denied_admin_portal():
    """demo-bob is a player → GET /admin is forbidden (403)."""
    client = await _client("demo-bob@example.com")
    try:
        resp = await client.get("/admin")
        assert resp.status_code == 403, resp.text
    finally:
        await client.aclose()


async def test_demo_gm2_denied_admin_portal():
    """v2.591.0 — demo-gm2 holds the app-wide GM role but is NOT site-admin,
    so GET /admin is forbidden (403). Locks in that the GM role and the admin
    console are independent."""
    client = await _client("demo-gm2@example.com")
    try:
        resp = await client.get("/admin")
        assert resp.status_code == 403, resp.text
    finally:
        await client.aclose()


async def test_demo_new_players_denied_admin_portal():
    """v2.591.0 — the new shared players are never admin → 403."""
    for email in ("demo-carol@example.com", "demo-dave@example.com", "demo-erin@example.com"):
        client = await _client(email)
        try:
            resp = await client.get("/admin")
            assert resp.status_code == 403, f"{email}: {resp.text}"
        finally:
            await client.aclose()
