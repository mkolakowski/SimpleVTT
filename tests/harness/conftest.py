"""Pytest fixtures for the SimpleVTT click-through test harness.

Provides per-user authenticated httpx clients + WS collectors, plus a
``roster`` lookup keyed by character name (the demo's character IDs
are autoincremented and vary across resets, so test code names
characters, not numbers).

Phase 1 scope: covers the demo's three PCs (Pip / Thalindra / Tavik)
through the existing demo accounts. Phase 1.5 will add test-fixture
PCs in a sidecar test campaign per docs/plans/test-harness.md.
"""
from __future__ import annotations

import asyncio
import os
from typing import AsyncIterator

import httpx
import pytest
import pytest_asyncio

from .helpers import WSCollector, login_client, open_ws


CAMPAIGN_ID = int(os.getenv("HARNESS_TEST_CAMPAIGN", "1"))


@pytest_asyncio.fixture
async def gm_client() -> AsyncIterator[httpx.AsyncClient]:
    """GM-authenticated client. Function-scoped — pytest-asyncio's
    default function-scope event loop forces this; trying to share a
    session-scoped httpx client across tests would cross event loops
    and trip "Future attached to a different loop" errors. Each test
    logs in fresh (~50-100 ms per login; negligible at suite scale).
    """
    client = await login_client("demo-gm@example.com", "demopass")
    try:
        yield client
    finally:
        await client.aclose()


@pytest_asyncio.fixture
async def alice_client() -> AsyncIterator[httpx.AsyncClient]:
    client = await login_client("demo-alice@example.com", "demopass")
    try:
        yield client
    finally:
        await client.aclose()


@pytest_asyncio.fixture
async def bob_client() -> AsyncIterator[httpx.AsyncClient]:
    client = await login_client("demo-bob@example.com", "demopass")
    try:
        yield client
    finally:
        await client.aclose()


@pytest_asyncio.fixture
async def roster(gm_client: httpx.AsyncClient) -> dict[str, dict]:
    """Demo campaign roster keyed by character name. Test code looks
    up ``roster["Pip Quickfingers"]["id"]`` for the canonical PC id.
    """
    resp = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/roster")
    assert resp.status_code == 200, f"roster fetch failed: {resp.status_code}"
    data = resp.json()
    by_name = {c["name"]: c for c in data["characters"]}
    # Smoke-check: the eight demo PCs are present (Paladin v2.14.0,
    # Bard v2.14.1, Druid v2.14.2, Fighter v2.17.0, Monk v2.18.0).
    # If this fails the demo seed has drifted and every downstream
    # test will fail mysteriously — better to fail fast here.
    expected = {
        "Pip Quickfingers",
        "Thalindra Moonwhisper",
        "Brother Tavik Stonebrow",
        "Sir Caelan Lightbringer",
        "Lyra Sunstrider",
        "Mira Greenleaf",
        "Garrik Ironside",
        "Kael Brightleaf",
    }
    missing = expected - set(by_name)
    if missing:
        raise AssertionError(f"Demo roster is missing: {missing}. Got: {list(by_name)}")
    return by_name


@pytest_asyncio.fixture
async def gm_ws(gm_client: httpx.AsyncClient) -> AsyncIterator[WSCollector]:
    """GM-authenticated WS connection to the demo campaign with a
    background message collector. Test-scoped (closes between tests)
    so each test starts with a fresh buffer.
    """
    ws = await open_ws(gm_client, CAMPAIGN_ID)
    try:
        async with WSCollector(ws) as collector:
            yield collector
    finally:
        await ws.close()


@pytest_asyncio.fixture
async def alice_ws(alice_client: httpx.AsyncClient) -> AsyncIterator[WSCollector]:
    ws = await open_ws(alice_client, CAMPAIGN_ID)
    try:
        async with WSCollector(ws) as collector:
            yield collector
    finally:
        await ws.close()


@pytest_asyncio.fixture
async def bob_ws(bob_client: httpx.AsyncClient) -> AsyncIterator[WSCollector]:
    ws = await open_ws(bob_client, CAMPAIGN_ID)
    try:
        async with WSCollector(ws) as collector:
            yield collector
    finally:
        await ws.close()
