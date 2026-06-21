"""``POST /admin/demo/reset`` — on-demand demo reseed (v2.3.0).

Regression coverage for the v2.495.2 actor-after-reseed fix: the demo
GM is the demo's only admin, so when *it* triggers the reset,
``reset_and_reseed`` wipes and re-creates that very user mid-request.
The handler used to touch the now-deleted ``user`` ORM object
afterward (logging ``user.email``, auditing with ``actor=user``),
which 500'd with ObjectDeletedError / an FK violation even though the
reseed itself committed. The fix captures the actor email up front and
re-resolves the recreated row before auditing.

These tests require ``DEMO_GM_SITE_ADMIN`` on (the default, and what CI
runs) so demo-gm is an admin able to reach the endpoint. They reseed
the demo dataset, which ``_reset_sequences`` keeps pinned at campaign
id 1, so the rest of the suite is unaffected.

Coverage:
  - Happy path: demo-gm (a demo actor) triggers reset → 200 + counts,
    NOT a 500 from the wiped-actor bug.
  - 403 when a non-admin player hits it.
"""
from __future__ import annotations

import httpx

from .helpers import login_client


async def test_admin_demo_reset_succeeds_for_demo_actor():
    """demo-gm triggers its own wipe+reseed → 200, not 500.

    Reproduces the actor-after-reseed bug: without the fix the handler
    500s on the recreated-actor; with it, the response is a clean 200
    carrying the per-section counts.
    """
    admin = await login_client("demo-gm@example.com", "demopass")
    try:
        resp = await admin.post("/admin/demo/reset")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["ok"] is True
        # counts carries the seed per-section dict; campaign stays at 1.
        assert isinstance(body.get("counts"), dict)
        assert body["counts"].get("campaign") == 1
    finally:
        await admin.aclose()


async def test_admin_demo_reset_forbidden_for_player():
    """A non-admin player (demo-alice) → 403."""
    alice = await login_client("demo-alice@example.com", "demopass")
    try:
        resp = await alice.post("/admin/demo/reset")
        assert resp.status_code == 403, resp.text
    finally:
        await alice.aclose()
