"""B17 (v2.1033.7) — the ``hermetic_pcs`` autouse fixture heals a leaked
sheet strip between tests.

Regression guard for the CI ``harness`` cascade: a sheet-mutating test that
strips a PC's ``spells`` / ``resources`` and whose own restore doesn't
complete must NOT leave the PC stripped for the next test. The
``hermetic_pcs`` fixture (conftest) snapshots each PC's pristine mutable
sheet on the first test and restores drifted fields before every subsequent
test. These two tests exercise that directly:

  1. ``test_leak_strips_spells`` empties Thalindra's ``spells`` list and does
     NOT restore it (simulating a forgotten / aborted restore).
  2. ``test_next_test_sees_restored_spells`` — which runs after (1) in file
     order — asserts Thalindra's spells are back, proving the fixture healed
     the leak at this test's setup.

Also asserts the fixture's snapshot/restore helpers round-trip a resource
strip within a single test.
"""
import pytest_asyncio

from .conftest import (
    CAMPAIGN_ID,
    _read_sheet,
    _restore_pristine,
    _snapshot_pristine,
)


@pytest_asyncio.fixture
async def thalindra(roster):
    return roster["Thalindra Moonwhisper"]


async def _spell_count(gm_client, char_id) -> int:
    sheet = await _read_sheet(gm_client, char_id)
    return len(sheet.get("spells") or [])


async def test_leak_strips_spells(gm_client, thalindra):
    """Strip the caster's spells and deliberately leak (no restore)."""
    char_id = thalindra["id"]
    assert await _spell_count(gm_client, char_id) > 0, "caster should start with spells"

    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"spells": []},
    )
    assert r.status_code == 200, r.text
    assert await _spell_count(gm_client, char_id) == 0, "strip should have taken effect"
    # Intentionally no restore — hermetic_pcs must clean this up for the next test.


async def test_next_test_sees_restored_spells(gm_client, thalindra):
    """The fixture restored the leaked strip at this test's setup."""
    assert await _spell_count(gm_client, thalindra["id"]) > 0, (
        "hermetic_pcs did not restore the caster's spells stripped by the "
        "prior test — the B17 cascade guard is broken"
    )


async def test_snapshot_restore_helper_round_trips(gm_client, thalindra):
    """The snapshot/restore helpers heal a strip within a single test."""
    char_id = thalindra["id"]
    pristine = await _snapshot_pristine(gm_client, char_id)
    assert pristine.get("spells"), "snapshot should capture the caster's spells"

    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"spells": []},
    )
    assert await _spell_count(gm_client, char_id) == 0

    await _restore_pristine(gm_client, char_id, pristine)
    restored = (await _read_sheet(gm_client, char_id)).get("spells") or []
    assert restored == pristine["spells"], "restore should return the exact pristine list"
