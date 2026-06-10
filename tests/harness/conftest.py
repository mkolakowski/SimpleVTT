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
    # Smoke-check: the demo PCs are present — Phase A wraps with
    # v2.18.4 covering all 12 PHB classes (Barbarian / Bard / Cleric /
    # Druid / Fighter / Monk / Paladin / Ranger / Rogue / Sorcerer /
    # Warlock / Wizard); v2.158.56 adds a 13th PC, a Vengeance Paladin
    # (Dame Seraphine Vael), so the Vow of Enmity sheet button has a
    # live demo fixture; v2.158.60 adds a 14th, a Path of the Beast
    # Barbarian (Brakka Wildmane), so the Form of the Beast button has
    # one too; v2.158.62 adds a 15th, a Way of the Drunken Master Monk
    # (Quan Reelstep), so the Drunken Technique button has one too. If
    # this fails the demo seed has drifted and every downstream test
    # will fail mysteriously — better to fail fast here.
    expected = {
        "Pip Quickfingers",
        "Thalindra Moonwhisper",
        "Brother Tavik Stonebrow",
        "Sir Caelan Lightbringer",
        "Lyra Sunstrider",
        "Mira Greenleaf",
        "Garrik Ironside",
        "Kael Brightleaf",
        "Zara Emberfire",
        "Krieger Stonefist",
        "Rowan Quickbow",
        "Magnus Hexbinder",
        "Dame Seraphine Vael",
        "Brakka Wildmane",
        "Quan Reelstep",
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


# v2.99.5 — session-level PC state reset fixture.
#
# Tests that depend on a PC starting from a known-clean state can
# request ``clean_pcs`` to long-rest every demo PC + clear a known
# set of persistent buff keys from each one. Use this when a prior
# test's state leak (Frightened from Fear tests, Stunned from
# Stunning Strike tests, etc.) would silently degrade the PC's
# capability — most commonly to-hit penalties from Frightened /
# Prone / Blinded, or auto-fail STR/DEX saves from Paralyzed.
#
# This is NOT ``autouse=True`` because it adds ~1s per test it runs
# on (12 long_rest calls + 12×N end_buff no-ops). Tests that don't
# need cross-suite state isolation skip it for speed; tests that DO
# need it pay the cost.
#
# Filed as a follow-up: when the per-test cost is acceptable, flip
# this to ``autouse=True`` and remove the per-test cleanup blocks
# in test_use_repeated_save, test_pfeag_condition_immunity,
# test_npc_concentration, test_aura_of_devotion, etc.

# Persistent buff keys that commonly leak between tests + affect
# attack rolls / saves / to-hit. Future content adds keys here when
# it lands.
_LEAKABLE_BUFF_KEYS = (
    "frightened", "paralyzed", "stunned", "prone", "blinded",
    "incapacitated", "unconscious", "asleep", "charmed",
    "baned", "faerie-fired", "confused", "banished",
    "heroism", "bless", "shield-of-faith", "sacred-weapon",
    "bardic-inspiration-die", "protection-from-evil-and-good",
    "rage", "metamagic-empowered-pending",
    "concentration-hex", "concentration-hunters-mark",
    "concentration-hold-person", "concentration-fear",
    "concentration-bless", "concentration-bane",
    "concentration-faerie-fire", "concentration-banishment",
    "concentration-confusion", "concentration-suggestion",
    "concentration-hideous-laughter",
)


@pytest_asyncio.fixture(autouse=True)
async def clean_pcs(
    gm_client: httpx.AsyncClient, roster: dict[str, dict],
) -> dict[str, dict]:
    """v2.99.5 — long-rest every PC + clear all known persistent
    buff keys. Used by suite-contention-sensitive tests as a per-
    test reset gate. Returns the roster dict so callers can chain
    ``roster = clean_pcs`` in their signature without an extra
    fixture request.

    v2.99.6 — ``autouse=True``. The fixture now runs before every
    test that has access to gm_client + roster (which is most of
    the harness suite). Adds ~1s per test for the 12 long-rests +
    end_buff calls, but eliminates cross-test state leak at the
    cost of suite runtime (~5.5 min → ~17 min). The trade-off is
    deterministic test pass rates over speed.
    """
    for char in roster.values():
        char_id = char["id"]
        for key in _LEAKABLE_BUFF_KEYS:
            await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/end_buff",
                json={"character_id": char_id, "key": key},
            )
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
            json={"type": "long"},
        )
    return roster
