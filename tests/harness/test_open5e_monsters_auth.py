"""Harness test for the /api/open5e/monsters auth gate (v2.1041.1).

Like the item proxy (v2.1040.2), the monster-search proxy is an outbound
server-side request primitive; it now requires login. Only the error path
(unauthenticated → 401) is asserted — the happy path issues a live outbound
call.
"""
from __future__ import annotations

import httpx

from .helpers import BASE_URL


async def test_open5e_monsters_requires_auth():
    async with httpx.AsyncClient(base_url=BASE_URL) as c:
        r = await c.get("/api/open5e/monsters?search=goblin&limit=5")
    assert r.status_code == 401, r.text
