"""v2.369.0 — Unarmored Defense auto-AC engine (Barbarian / Monk Lv 1+).

Closes the two 🟡 rows on the v2.344.3 reconciliation
(class-content-status.md lines 658 + 727 — Barbarian Lv 1 Unarmored
Defense + Monk Lv 1 Unarmored Defense). New `_pc_unarmored_defense_ac`
helper computes the RAW formula:

- Barbarian: 10 + DEX mod + CON mod (no armor; shield OK).
- Monk: 10 + DEX mod + WIS mod (no armor; no shield).

`_read_target_ac` takes max(stored, computed) so seeded ACs (Krieger
AC 15, Kael AC 16 — both equal the formula at their default ability
scores) stay intact, but a PATCH to ability scores flows directly to
the read site without a second `sheet.ac` PATCH.

Tests:
  - Krieger baseline (DEX 14 / CON 16 / Lv 7 Barb) → AC reads 15 via
    formula (same as stored).
  - Krieger CON 16 → 20 (PATCH) → AC auto-rises to 16.
  - Kael baseline (DEX 18 / WIS 15 / Lv 7 Monk) → AC reads 16.
  - Kael WIS 15 → 19 (PATCH) → AC auto-rises to 18.
  - Monk wielding a shield → formula skipped (RAW gate). PATCH a
    shield onto Kael, verify the formula doesn't fire.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _mkc(cid, char_id=None, name="X", hp_max=80):
    return {
        "id": cid, "char_id": char_id, "name": name,
        "initiative": 10, "hp_current": hp_max, "hp_max": hp_max,
        "ac": 1, "buffs": [], "creature_type": "humanoid",
        "speed_walk": 30,
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _seed_battle(gm_client, combatants):
    return await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


async def _read_target_ac_via_attack(gm_client, attacker, target_cid, attack_idx=0):
    """Trigger an /attack call from `attacker` against `target_cid` so
    the response carries the resolved `target_ac`. Returns the
    target_ac integer (or None if missing). We don't care about the
    hit/damage — just the AC value."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": attacker["id"],
            "attack_index": attack_idx,
            "target_combatant_id": target_cid,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json().get("target_ac")


async def _sheet(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    return (r.json() or {}).get("sheet") or {}


async def _patch_abilities(gm_client, char_id, new_abilities):
    sheet = await _sheet(gm_client, char_id)
    snap = dict(sheet.get("abilities") or {})
    merged = {**snap, **new_abilities}
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"abilities": merged},
    )
    return snap


async def _restore_abilities(gm_client, char_id, snap):
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"abilities": snap},
    )


async def _patch_inventory(gm_client, char_id, inventory):
    sheet = await _sheet(gm_client, char_id)
    snap = list(sheet.get("inventory") or [])
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"inventory": inventory},
    )
    return [dict(it) if isinstance(it, dict) else it for it in snap]


async def _restore_inventory(gm_client, char_id, snap):
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"inventory": snap},
    )


@pytest_asyncio.fixture
async def caelan(roster):
    return roster["Sir Caelan Lightbringer"]


@pytest_asyncio.fixture
async def krieger(roster):
    return roster["Krieger Stonefist"]


@pytest_asyncio.fixture
async def kael(roster):
    return roster["Kael Brightleaf"]


async def test_barbarian_unarmored_defense_baseline(
    gm_client, caelan, krieger,
):
    """Krieger (Half-Orc Barbarian Lv 7, DEX 14 / CON 16, no armor) →
    Unarmored Defense AC = 10 + 2 + 3 = 15. Matches the seeded
    `sheet.ac: 15`."""
    krieger_cid = f"tok_ud_krieger_baseline_{krieger['id']}"
    caelan_cid = f"tok_ud_caelan_{caelan['id']}"
    await _seed_battle(gm_client, [
        _mkc(caelan_cid, caelan["id"], name=caelan["name"]),
        _mkc(krieger_cid, krieger["id"], name=krieger["name"]),
    ])
    ac = await _read_target_ac_via_attack(gm_client, caelan, krieger_cid)
    assert ac == 15, (
        f"baseline Unarmored Defense AC for Krieger should be 15 "
        f"(10 + DEX +2 + CON +3); got {ac!r}"
    )


async def test_barbarian_unarmored_defense_tracks_con_bump(
    gm_client, caelan, krieger,
):
    """PATCH Krieger CON 16 → 20 → Unarmored Defense AC auto-rises
    from 15 → 17 (CON mod +3 → +5). Restores in finally."""
    snap = await _patch_abilities(gm_client, krieger["id"], {"CON": 20})
    try:
        krieger_cid = f"tok_ud_krieger_conbump_{krieger['id']}"
        caelan_cid = f"tok_ud_caelan_conbump_{caelan['id']}"
        await _seed_battle(gm_client, [
            _mkc(caelan_cid, caelan["id"], name=caelan["name"]),
            _mkc(krieger_cid, krieger["id"], name=krieger["name"]),
        ])
        ac = await _read_target_ac_via_attack(gm_client, caelan, krieger_cid)
        assert ac == 17, (
            f"Krieger CON 20 → Unarmored Defense AC should be 17 "
            f"(10 + DEX +2 + CON +5); got {ac!r}"
        )
    finally:
        await _restore_abilities(gm_client, krieger["id"], snap)


async def test_monk_unarmored_defense_baseline(gm_client, caelan, kael):
    """Kael (Wood Elf Monk Lv 7, DEX 18 / WIS 15, no armor / no shield) →
    Unarmored Defense AC = 10 + 4 + 2 = 16. Matches the seeded
    `sheet.ac: 16`."""
    kael_cid = f"tok_ud_kael_baseline_{kael['id']}"
    caelan_cid = f"tok_ud_caelan_kael_{caelan['id']}"
    await _seed_battle(gm_client, [
        _mkc(caelan_cid, caelan["id"], name=caelan["name"]),
        _mkc(kael_cid, kael["id"], name=kael["name"]),
    ])
    ac = await _read_target_ac_via_attack(gm_client, caelan, kael_cid)
    assert ac == 16, (
        f"baseline Unarmored Defense AC for Kael should be 16 "
        f"(10 + DEX +4 + WIS +2); got {ac!r}"
    )


async def test_monk_unarmored_defense_tracks_wis_bump(
    gm_client, caelan, kael,
):
    """PATCH Kael WIS 15 → 19 → AC auto-rises from 16 → 18
    (WIS mod +2 → +4). Restores in finally."""
    snap = await _patch_abilities(gm_client, kael["id"], {"WIS": 19})
    try:
        kael_cid = f"tok_ud_kael_wisbump_{kael['id']}"
        caelan_cid = f"tok_ud_caelan_wisbump_{caelan['id']}"
        await _seed_battle(gm_client, [
            _mkc(caelan_cid, caelan["id"], name=caelan["name"]),
            _mkc(kael_cid, kael["id"], name=kael["name"]),
        ])
        ac = await _read_target_ac_via_attack(gm_client, caelan, kael_cid)
        assert ac == 18, (
            f"Kael WIS 19 → Unarmored Defense AC should be 18 "
            f"(10 + DEX +4 + WIS +4); got {ac!r}"
        )
    finally:
        await _restore_abilities(gm_client, kael["id"], snap)


async def test_monk_shield_disables_unarmored_defense(
    gm_client, caelan, kael,
):
    """PATCH a shield onto Kael's inventory → Monk Unarmored Defense
    formula skips (RAW: "not wielding a shield"). The seeded `sheet.ac:
    16` still wins via the max() floor, but a PATCH to a higher
    ability score should NOT raise it further — proves the formula
    gate. Concretely: drop CON 14 → 8 (no shield: AC stays 16 since
    that's the seeded base; with shield equipped: should still be 16
    since formula bypassed and stored AC is the only source)."""
    inv_snap = await _patch_inventory(gm_client, kael["id"], [
        {
            "name": "Test Shield", "type": "shield", "qty": 1,
            "equippable": True, "equipped": True, "hands": 1,
            "_slug": "shield",
        },
    ])
    try:
        # Bump Kael's WIS to 25 — if Unarmored Defense were still
        # firing, AC would rise to 10 + 4 + 7 = 21. With the shield
        # gate, it stays at the stored 16 (the floor).
        wis_snap = await _patch_abilities(gm_client, kael["id"], {"WIS": 25})
        try:
            kael_cid = f"tok_ud_kael_shield_{kael['id']}"
            caelan_cid = f"tok_ud_caelan_shield_{caelan['id']}"
            await _seed_battle(gm_client, [
                _mkc(caelan_cid, caelan["id"], name=caelan["name"]),
                _mkc(kael_cid, kael["id"], name=kael["name"]),
            ])
            ac = await _read_target_ac_via_attack(gm_client, caelan, kael_cid)
            assert ac == 16, (
                f"Kael wielding a shield should NOT pick up Unarmored "
                f"Defense (Monk gate excludes shield); WIS-25 hike should "
                f"not raise AC above the seeded 16. Got {ac!r}"
            )
        finally:
            await _restore_abilities(gm_client, kael["id"], wis_snap)
    finally:
        await _restore_inventory(gm_client, kael["id"], inv_snap)
