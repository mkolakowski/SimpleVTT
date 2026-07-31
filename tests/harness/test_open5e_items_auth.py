"""Harness test for the /api/open5e/items auth gate (v2.1040.2).

The Open5e item-search proxy is an outbound server-side request primitive; it
now requires login so an anonymous visitor can't use it as a request relay.
Only the error path (unauthenticated → 401) is asserted — the happy path would
issue a live outbound call to Open5e.
"""
from __future__ import annotations

import httpx

from .helpers import BASE_URL


async def test_open5e_items_requires_auth():
    async with httpx.AsyncClient(base_url=BASE_URL) as c:
        r = await c.get("/api/open5e/items?type=weapons&search=sword&limit=5")
    assert r.status_code == 401, r.text
