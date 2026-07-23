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

v2.1033.11 (B18 class 1) adds class-scoped level/subclass leak/restore guards.
v2.1033.12 (B18 class 3) adds a guard that `clean_pcs` clears a leaked buff
whose key isn't in the hardcoded `_LEAKABLE_BUFF_KEYS`.
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


async def _level(gm_client, char_id) -> int:
    sheet = await _read_sheet(gm_client, char_id)
    return int(sheet.get("level") or 0)


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
    assert pristine["top"].get("spells"), "snapshot should capture the caster's spells"

    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"spells": []},
    )
    assert await _spell_count(gm_client, char_id) == 0

    await _restore_pristine(gm_client, char_id, pristine)
    restored = (await _read_sheet(gm_client, char_id)).get("spells") or []
    assert restored == pristine["top"]["spells"], "restore should return the exact pristine list"


# ── B18 class 1: class-scoped level/subclass restore ─────────────────────────

async def test_leak_bumps_level(gm_client, thalindra):
    """Change the caster's class-scoped level and deliberately leak it
    (no restore) — hermetic_pcs must heal it for the next test."""
    char_id = thalindra["id"]
    seed_level = await _level(gm_client, char_id)
    assert seed_level == 7, f"Thalindra should seed at Lv 7, got {seed_level}"

    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"level": 3, "class_slug": "wizard"},
    )
    assert r.status_code == 200, r.text
    assert await _level(gm_client, char_id) == 3, "level bump should have taken effect"
    # Intentionally no restore.


async def test_next_test_sees_restored_level(gm_client, thalindra):
    """The fixture restored the class-scoped level drift at this test's setup."""
    assert await _level(gm_client, thalindra["id"]) == 7, (
        "hermetic_pcs did not restore the caster's class-scoped level bumped "
        "by the prior test — the B18 class-1 / B9 guard is broken"
    )


async def test_class_scoped_restore_round_trips(gm_client, thalindra):
    """`_restore_pristine` heals a class-scoped level change within one test."""
    char_id = thalindra["id"]
    pristine = await _snapshot_pristine(gm_client, char_id)
    assert pristine["cls"].get("level") == 7
    assert pristine["slug"] == "wizard", f"primary class_slug should be wizard, got {pristine['slug']!r}"

    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"level": 3, "class_slug": "wizard"},
    )
    assert await _level(gm_client, char_id) == 3

    await _restore_pristine(gm_client, char_id, pristine)
    assert await _level(gm_client, char_id) == 7, "class-scoped restore should return level to 7"


# ── B18 class 3: clean_pcs clears any leaked buff (not just the hardcoded list) ─

async def _garrik_buff_keys(gm_client, garrik_id) -> set:
    b = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/battle")).json().get("battle") or {}
    for cbt in b.get("combatants") or []:
        if cbt.get("char_id") == garrik_id:
            return {(x or {}).get("key") for x in (cbt.get("buffs") or [])}
    return set()


async def test_leak_nonhardcoded_buff(gm_client, roster):
    """Install a buff whose key is NOT in `_LEAKABLE_BUFF_KEYS`
    (`resistance-cold` from a Potion of Resistance drink) on Garrik's
    combatant and leak it — `clean_pcs` must clear it for the next test."""
    garrik = roster["Garrik Ironside"]
    sheet = await _read_sheet(gm_client, garrik["id"])
    idx = next(i for i, it in enumerate(sheet.get("inventory") or [])
               if (it.get("_slug") or "") == "potion-of-resistance")
    await gm_client.put(f"/api/campaign/{CAMPAIGN_ID}/battle", json={"combatants": [{
        "id": "tok_hermetic_garrik", "char_id": garrik["id"], "name": "Garrik Ironside",
        "initiative": 10, "hp_current": 85, "hp_max": 85, "buffs": []}]})
    drink = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/use_item_action",
        json={"inventory_index": idx, "action_key": "drink"})
    assert drink.status_code == 200, drink.text
    assert drink.json().get("buff_installed") is True
    assert any(str(k).startswith("resistance-")
               for k in await _garrik_buff_keys(gm_client, garrik["id"]))
    # Intentionally no cleanup — clean_pcs must handle it.


async def test_next_test_sees_cleared_buff(gm_client, roster):
    """The leaked non-hardcoded buff was cleared by `clean_pcs` at setup."""
    garrik = roster["Garrik Ironside"]
    keys = await _garrik_buff_keys(gm_client, garrik["id"])
    assert not any(str(k).startswith("resistance-") for k in keys), (
        f"clean_pcs did not clear the leaked resistance buff; Garrik has {keys}"
    )
    # Tidy up the battle we leaked so we don't pollute the rest of the run.
    await gm_client.put(f"/api/campaign/{CAMPAIGN_ID}/battle", json={"combatants": []})


# ── B18 class 2: hermetic_battle restores the seeded battle roster ────────────

async def _seeded_token_ids(gm_client) -> set:
    b = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/battle")).json().get("battle") or {}
    return {c.get("source_token_id") for c in (b.get("combatants") or []) if c.get("source_token_id")}


async def test_leak_battle_roster(gm_client):
    """Overwrite the demo's seeded battle with a custom combatant and leak
    it — `hermetic_battle` must restore the seeded roster for the next test."""
    assert len(await _seeded_token_ids(gm_client)) >= 4, "demo should seed ≥4 combatants"
    r = await gm_client.put(f"/api/campaign/{CAMPAIGN_ID}/battle", json={
        "combatants": [{"id": "tok_battle_leak", "char_id": None, "name": "Dummy",
                        "initiative": 1, "hp_current": 1, "hp_max": 1, "buffs": []}],
        "turn_index": 0, "round": 1, "active": True})
    assert r.status_code == 200
    assert await _seeded_token_ids(gm_client) == set(), "seeded roster should be gone after the overwrite"
    # Intentionally no restore.


async def test_next_test_sees_restored_battle(gm_client):
    """`hermetic_battle` restored the seeded combatant roster at this test's setup."""
    assert len(await _seeded_token_ids(gm_client)) >= 4, (
        "hermetic_battle did not restore the demo's seeded battle roster that the "
        "prior test overwrote — the B18 class-2 guard is broken"
    )
