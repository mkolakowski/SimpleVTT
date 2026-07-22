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
import copy
import os
from pathlib import Path
from typing import AsyncIterator

import httpx
import pytest
import pytest_asyncio

from .helpers import WSCollector, login_client, open_ws


CAMPAIGN_ID = int(os.getenv("HARNESS_TEST_CAMPAIGN", "1"))


# v2.183.23 — spell-validation suite Phase 5. Auto-tag the
# spell-validation files with the ``spell_catalog`` marker by filename
# so the dedicated CI job (`pytest -m spell_catalog`) selects them
# without a hand-maintained path list. New spell-validation files join
# the job automatically as long as they follow the naming convention:
# the catalog-iterating Phase 1-2 files (``test_spell_*``), the Phase
# 3-4 per-spell deep-dives (``test_cast_*``), plus the AC-buff deep-dive
# (``test_ac_buff_spells``). The marker is also useful locally —
# ``pytest tests/harness/ -m spell_catalog`` runs just the spell suite.
_SPELL_CATALOG_PREFIXES = ("test_spell_", "test_cast_")
_SPELL_CATALOG_EXACT = {"test_ac_buff_spells.py"}


def pytest_collection_modifyitems(config, items):
    for item in items:
        fn = Path(str(item.fspath)).name
        if fn.startswith(_SPELL_CATALOG_PREFIXES) or fn in _SPELL_CATALOG_EXACT:
            item.add_marker("spell_catalog")


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


@pytest_asyncio.fixture
async def bright_map(gm_client: httpx.AsyncClient):
    """v2.1033.2 (B16) — force the active demo map to ``bright`` ambient
    for the duration of a vision-sensitive test, then restore the demo's
    canonical ``dim``.

    Ambient-light state on the shared demo map **leaks between harness
    tests**: several vision tests set the active map to ``dark`` and don't
    reset it. A downstream spell-effect gate test that asserts an exact
    attack roll-state — e.g. Blur's ``disadvantage_blur``, or the
    ``target_invisible`` edge for True Seeing / Mislead — then reads
    ``canceled_unseen_attacker_vs_*`` instead, because the attacker can't
    see the target in the inherited darkness, and the can't-see
    cancellation pre-empts the effect under test. (These tests all pass in
    isolation on the canonical ``dim`` map; they only fail after a
    ``dark``-leaving test, which is why CI's full-suite run is red while a
    single-file run is green.)

    Forcing ``bright`` fires the engine's vision short-circuit
    (``_attack_vision_edges`` returns ``(False, False)`` on a bright map
    with no emitters), so the assertion tests the spell mechanic rather
    than the ambient light. Restoring ``dim`` in teardown — which runs even
    when the test body asserts — also heals the leaked state for whatever
    runs next. Opt-in (not autouse) like ``clean_pcs``: only the
    vision-sensitive gate tests pay the two extra POSTs.
    """
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")
    map_id = int(r.json()["map_id"])

    async def _set(value: str) -> None:
        resp = await gm_client.post(
            f"/campaign/{CAMPAIGN_ID}/settings/maps/{map_id}/ambient_light",
            json={"ambient_light": value},
        )
        assert resp.status_code == 200, resp.text

    await _set("bright")
    try:
        yield map_id
    finally:
        await _set("dim")


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


# ── B17: hermetic sheet snapshot/restore (autouse) ───────────────────────────
#
# The CI ``harness`` job runs the whole non-catalog suite serially against one
# shared demo stack. ~500 tests mutate a PC's sheet — they PATCH ``spells`` /
# ``spell_slots`` / ``resources`` / ``attacks`` / ``abilities`` via
# ``/sheet-fields`` and rely on their own restore-in-``finally`` block. When one
# of those restores doesn't complete (an assertion aborts the body before the
# finally, a ``pkill``'d run skips teardown, a test simply forgot to restore),
# the PC is left stripped and **every downstream test that needs that PC's
# spells/resources fails** — the B17 cascade (~97% of the CI job: "Thalindra
# has no Fireball", "No Ki / Lay on Hands / Channel Divinity resource",
# "assert 5 == 7"). ``clean_pcs`` can't recover this: a long rest refills slot
# *counts* and resource *uses*, but never re-adds a *deleted* spell or a
# *removed* resource object.
#
# This autouse fixture makes the suite hermetic against that class of leak:
# it snapshots each demo PC's pristine mutable sheet fields once (on the first
# test, when the freshly-seeded stack is clean — the workflow's sanity-check
# step guarantees this), then before every subsequent test restores any field
# that drifted from pristine. A single test's failed restore is healed at the
# next test's setup, so it can no longer cascade.
#
# Scope note: restores both **top-level** keys (bare ``/sheet-fields`` PATCH —
# ``/rest``'s normalize doesn't recompute them, so a guaranteed-safe round-trip)
# and, since v2.1033.11 (B18 class 1), the **class-scoped** ``level`` /
# ``subclass`` / ``subclass_*`` fields (restored in a separate PATCH carrying the
# PC's primary ``class_slug`` so normalize can't undo them). The top-level set
# was B17's cascade signature (spells/resources); the class-scoped set is the
# level/subclass drift that left ``test_touch_of_death`` reading
# ``monk_level == 5`` (and closes B9). See ``_SHEET_PATCH_KEYS`` /
# ``_CLASS_SCOPED_KEYS`` in ``app/routes/tabletop_routes.py``.

# Pristine per-PC sheet snapshots, keyed by character id. A plain module-level
# dict (pure data, no event-loop affinity) so it can be shared across the
# function-scoped tests where a live session-scoped httpx client would cross
# event loops and trip "Future attached to a different loop" (see the
# ``gm_client`` note above). Populated lazily on the first test.
_PRISTINE_SHEETS: dict[int, dict] = {}

# Top-level sheet keys a sheet-mutating test can strip/replace and whose loss
# cascades. All are in ``_SHEET_PATCH_KEYS`` and NONE are in
# ``_CLASS_SCOPED_KEYS`` — so restoring them is a bare top-level PATCH.
_HERMETIC_RESTORE_KEYS = (
    "spells", "spell_slots", "resources", "attacks", "feats",
    "abilities", "saving_throws", "proficiency_bonus", "inventory",
    "damage_resistances", "damage_immunities", "damage_vulnerabilities",
    "condition_immunities", "creature_type", "fighting_style",
    "favorite_beasts", "hp_rolls",
)

# v2.1033.11 (B18 class 1) — class-scoped sheet keys. These are in
# ``_CLASS_SCOPED_KEYS``: a bare top-level PATCH is silently undone by the next
# ``/rest`` (whose ``normalize_dnd5e_sheet`` re-mirrors ``classes[0]`` over the
# top-level fields), so restoring them requires a ``class_slug`` so the PATCH
# writes the matching ``classes[]`` entry too. Level/subclass drift is what
# leaves ``test_touch_of_death`` reading ``monk_level == 5`` and
# ``test_potent_spellcasting`` seeing a leaked "light domain" — the B18 class-1
# residual. Snapshotting + restoring these (with the PC's primary class_slug)
# closes that class AND B9 (the Caelan level-bump coupling).
_HERMETIC_CLASS_SCOPED_KEYS = (
    "level", "subclass", "subclass_name", "subclass_flavor",
    "subclass_features", "subclass_choice", "subclass_features_data",
)


def _primary_class_slug(sheet: dict) -> str:
    """Slug of the PC's primary (first) class — the ``class_slug`` a
    class-scoped ``/sheet-fields`` PATCH needs so ``/rest``'s normalize
    doesn't undo it. Demo PCs are single-class, so ``classes[0]`` is
    the primary; all SRD class names are single words, so lower-casing
    (with spaces→hyphens for safety) matches the server's ``_class_slug``."""
    classes = sheet.get("classes") or []
    if classes and isinstance(classes[0], dict):
        return str(classes[0].get("class") or "").strip().lower().replace(" ", "-")
    return ""


async def _read_sheet(gm_client: httpx.AsyncClient, char_id: int) -> dict:
    """Return a PC's raw stored sheet dict (``/sheet-json`` gives the
    dnd5e-normalized ``char.sheet``, not a display projection — so its
    values round-trip back through ``/sheet-fields``)."""
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    if resp.status_code != 200:
        return {}
    return resp.json().get("sheet") or {}


async def _snapshot_pristine(gm_client: httpx.AsyncClient, char_id: int) -> dict:
    """Snapshot a PC's pristine restorable fields, split into ``top``
    (bare-PATCH keys) and ``cls`` (class-scoped keys, restored with the
    captured primary ``slug``)."""
    sheet = await _read_sheet(gm_client, char_id)
    return {
        "top": {k: copy.deepcopy(sheet[k])
                for k in _HERMETIC_RESTORE_KEYS if k in sheet},
        "cls": {k: copy.deepcopy(sheet[k])
                for k in _HERMETIC_CLASS_SCOPED_KEYS if k in sheet},
        "slug": _primary_class_slug(sheet),
    }


async def _restore_pristine(
    gm_client: httpx.AsyncClient, char_id: int, pristine: dict,
) -> None:
    """PATCH back any snapshot field that has drifted from pristine. Only
    writes on actual drift, so an untouched PC pays just the read.
    Class-scoped keys go in a separate PATCH carrying ``class_slug`` so
    ``/rest``'s normalize can't undo them."""
    if not pristine:
        return
    current = await _read_sheet(gm_client, char_id)
    url = f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields"
    top = pristine.get("top") or {}
    cls = pristine.get("cls") or {}
    slug = pristine.get("slug") or ""
    top_drift = {k: v for k, v in top.items() if current.get(k) != v}
    if top_drift:
        await gm_client.patch(url, json=top_drift)
    cls_drift = {k: v for k, v in cls.items() if current.get(k) != v}
    if cls_drift and slug:
        await gm_client.patch(url, json={**cls_drift, "class_slug": slug})


@pytest_asyncio.fixture(autouse=True)
async def hermetic_pcs(
    gm_client: httpx.AsyncClient, roster: dict[str, dict],
) -> None:
    """B17 / B18 — restore every demo PC's mutable sheet fields to their
    seed state before each test, so a sheet-mutating test whose own
    restore didn't complete can't cascade into the rest of the serial
    run. Covers both top-level fields (spells/resources/slots — the B17
    cascade) and class-scoped level/subclass (B18 class 1 / B9).

    Setup-time gate (like ``clean_pcs``, no teardown): the first test to
    run captures the pristine snapshot from the freshly-seeded stack;
    every test after that restores drifted fields first. Reads run
    concurrently across the ~15 PCs to keep the per-test cost near a
    single round-trip.
    """
    if not _PRISTINE_SHEETS:
        chars = list(roster.values())
        snaps = await asyncio.gather(
            *(_snapshot_pristine(gm_client, c["id"]) for c in chars)
        )
        for c, snap in zip(chars, snaps):
            _PRISTINE_SHEETS[c["id"]] = snap
        return
    await asyncio.gather(
        *(_restore_pristine(gm_client, cid, snap)
          for cid, snap in _PRISTINE_SHEETS.items()),
        return_exceptions=True,
    )


# ── Live progress + per-test timing (opt-in via HARNESS_PROGRESS=1) ──────────
# scripts/run_harness.sh sets HARNESS_PROGRESS=1 to stream a timestamped line
# when each test STARTS and again when it FINISHES (with its duration), so a
# long serial run shows live progress and a hang is pinpointed: a "▶" line
# with no follow-up "✓/✗" is the test currently stuck. Inert for normal runs —
# with the env var unset these hook functions are never defined, so pytest
# registers nothing.
import os as _hp_os  # noqa: E402
import datetime as _hp_dt  # noqa: E402

if _hp_os.getenv("HARNESS_PROGRESS") == "1":
    def pytest_runtest_logstart(nodeid, location):
        print(f"\n[{_hp_dt.datetime.now():%H:%M:%S}] ▶ {nodeid}", flush=True)

    def pytest_runtest_logreport(report):
        # The call phase is the test body; also surface any non-call failure
        # (a setup/teardown error) so fixture failures don't go silent.
        if report.when == "call" or (report.failed and report.when != "call"):
            mark = {"passed": "✓", "failed": "✗",
                    "skipped": "–"}.get(report.outcome, "?")
            print(
                f"[{_hp_dt.datetime.now():%H:%M:%S}] {mark} {report.nodeid} "
                f"({report.duration:.2f}s)",
                flush=True,
            )
