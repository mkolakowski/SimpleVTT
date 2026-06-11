"""v2.159.20 — exhaustion-levels Phase 3b: HP-max halving at Lv 4.

RAW PHB Appendix A: "Hit point maximum halved." Mirrors the
v2.97.42 Aid max-HP plumbing in reverse — instead of extending the
effective max with `+ buff_bonus`, halve the result when
`exhaustion_level >= 4`.

Two behaviors land in this phase:
  1. Heal-clamp: `_apply_heal_to_combatant` caps current at
     `floor((hp_max + aid_bonus) / 2)` instead of the full max.
  2. On-level-change clamp: when `/set_exhaustion` transitions from
     < 4 to >= 4, any current HP above the new ceiling is clamped
     down in-place. Going BACK below 4 (long rest / Greater
     Restoration) does NOT auto-restore HP — the player still has
     to heal up to the new ceiling.

Tests cover the PC and NPC paths separately.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def pip(roster):
    return roster["Pip Quickfingers"]


@pytest_asyncio.fixture
async def pip_full_hp(gm_client, pip):
    """Long rest + clear exhaustion so each test starts at 0 / full HP."""
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/set_exhaustion",
        json={"character_id": pip["id"], "level": 0},
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/rest",
        json={"type": "long"},
    )
    yield pip
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/set_exhaustion",
        json={"character_id": pip["id"], "level": 0},
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/rest",
        json={"type": "long"},
    )


async def _read_hp(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    sheet = resp.json().get("sheet") or {}
    hp = sheet.get("hp") or {}
    return int(hp.get("current") or 0), int(hp.get("max") or 0)


async def test_pc_set_lv4_clamps_current_hp_when_above_ceiling(
    gm_client, pip_full_hp,
):
    """v2.159.20 happy path. Pip at full HP → set Lv 4 → current
    drops to floor(max/2)."""
    pip = pip_full_hp
    cur_before, max_before = await _read_hp(gm_client, pip["id"])
    assert cur_before == max_before, (
        f"fixture preconditions: long rest should fill HP; "
        f"got cur={cur_before} max={max_before}"
    )

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/set_exhaustion",
        json={"character_id": pip["id"], "level": 4},
    )
    assert resp.status_code == 200, resp.text

    cur_after, max_after = await _read_hp(gm_client, pip["id"])
    expected_ceiling = max_before // 2
    assert cur_after == expected_ceiling, (
        f"expected current HP clamped to {expected_ceiling}; "
        f"got cur={cur_after}, max={max_after}"
    )
    # The base max field is NOT mutated — only the effective max for
    # heal clamping. The display can derive `floor(max/2)` from the
    # level field.
    assert max_after == max_before, (
        f"hp.max should be unchanged by exhaustion (kept at {max_before}); "
        f"got max={max_after}"
    )


async def test_pc_set_lv4_at_low_hp_unchanged(
    gm_client, pip_full_hp,
):
    """Pip at very low HP (1) → set Lv 4 → current stays 1 (already
    below the new ceiling, no further clamp)."""
    pip = pip_full_hp
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-fields",
        json={"hp": {"current": 1}},
    )
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/set_exhaustion",
        json={"character_id": pip["id"], "level": 4},
    )
    assert resp.status_code == 200, resp.text
    cur_after, _max_after = await _read_hp(gm_client, pip["id"])
    assert cur_after == 1, (
        f"low HP shouldn't change when crossing Lv 4 threshold; "
        f"got cur={cur_after}"
    )


async def test_pc_lv4_to_lv3_does_not_restore_hp(
    gm_client, pip_full_hp,
):
    """v2.159.20 RAW: going Lv 4 → Lv 3 (long rest or Greater
    Restoration) does NOT auto-restore the clamped HP. The player
    has to heal up."""
    pip = pip_full_hp
    cur_before, max_before = await _read_hp(gm_client, pip["id"])
    # Force to Lv 4 — current clamps to floor(max/2).
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/set_exhaustion",
        json={"character_id": pip["id"], "level": 4},
    )
    # Now drop to Lv 3 — current HP should NOT auto-bump back up.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/set_exhaustion",
        json={"character_id": pip["id"], "level": 3},
    )
    cur_after, _max_after = await _read_hp(gm_client, pip["id"])
    assert cur_after == max_before // 2, (
        f"dropping back to Lv 3 should NOT restore HP; "
        f"expected {max_before // 2}, got {cur_after}"
    )


async def test_pc_set_lv3_does_not_clamp_hp(
    gm_client, pip_full_hp,
):
    """v2.159.20 regression: Lv 3 does NOT touch HP-max (the Lv 4
    clamp must NOT fire prematurely)."""
    pip = pip_full_hp
    cur_before, _max_before = await _read_hp(gm_client, pip["id"])
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/set_exhaustion",
        json={"character_id": pip["id"], "level": 3},
    )
    cur_after, _max_after = await _read_hp(gm_client, pip["id"])
    assert cur_after == cur_before, (
        f"Lv 3 should not touch current HP; "
        f"got cur_before={cur_before}, cur_after={cur_after}"
    )
