"""v2.366.0 — magic-items: Shield of Missile Attraction (RAW DMG p.199,
rare, attunement, cursed). Bucket-B ranged-weapon damage-resistance
passive on the new `resistance_to_ranged_weapon` substrate. RAW: "While
holding this shield, you have resistance to damage from ranged weapon
attacks."

Folded into `_equipped_item_effects` + read by `_resistance_halve` when
called with `is_ranged_weapon_attack=True`. `_apply_damage_to_combatant`
threads the kwarg through; both /attack and /npc_attack compute the
flag via `_attack_is_ranged_weapon(attack)`.

Demo fixture: Dame Seraphine Vael carries the shield as inert Armory's
Remainder loot. The harness PATCHes inventory equipped+attuned and
uses Rowan Quickbow's Longbow (true ranged) vs Shortsword (melee) to
contrast the resistance gate.

Tests:
  - Ranged attack against the cursed shield's wearer halves piercing
    damage (the response's `target_resistance_applied` is True).
  - Melee attack against the wearer does NOT halve (resistance is
    ranged-only).
  - Equipped-but-unattuned → no resistance on either attack type.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


_SLUG = "shield-of-missile-attraction"
ROWAN_LONGBOW_ATTACK_IDX = 0
ROWAN_SHORTSWORD_ATTACK_IDX = 1


async def _seed_dice(gm_client, seed):
    r = await gm_client.post("/api/test/dice/seed", json={"seed": seed})
    assert r.status_code == 200, r.text


def _mkc(cid, char_id=None, name="X", hp_max=200):
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


async def _snapshot_inv(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    inv = list(((resp.json() or {}).get("sheet") or {}).get("inventory") or [])
    return [dict(it) if isinstance(it, dict) else it for it in inv]


async def _patch_inv(gm_client, char_id, *, equipped, attuned):
    snapshot = await _snapshot_inv(gm_client, char_id)
    new_inv = [dict(it) if isinstance(it, dict) else it for it in snapshot]
    found = False
    for it in new_inv:
        if isinstance(it, dict) and it.get("_slug") == _SLUG:
            it["equipped"] = equipped
            it["attuned"] = attuned
            found = True
    assert found, "Seraphine has no shield-of-missile-attraction inventory item"
    resp = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"inventory": new_inv},
    )
    assert resp.status_code == 200, resp.text
    return snapshot


async def _restore_inv(gm_client, char_id, snapshot):
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"inventory": snapshot},
    )


@pytest_asyncio.fixture
async def seraphine(roster):
    return roster["Dame Seraphine Vael"]


@pytest_asyncio.fixture
async def rowan(roster):
    return roster["Rowan Quickbow"]


async def _attack(gm_client, attacker, target_cid, attack_idx):
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": attacker["id"],
            "attack_index": attack_idx,
            "target_combatant_id": target_cid,
            "override": True,
            # Force auto-apply so the damage flow runs the resistance check.
        },
    )


async def _ensure_auto_apply(gm_client, enable):
    """Test-only endpoint to flip the auto_apply_damage flag — the
    resistance halving only runs when damage actually applies."""
    return await gm_client.post(
        f"/api/test/campaign/{CAMPAIGN_ID}/flags",
        json={"auto_apply_damage": enable},
    )


async def test_ranged_attack_resistance(gm_client, seraphine, rowan):
    """Shield equipped+attuned → Rowan's Longbow attack against
    Seraphine reports `target_resistance_applied: True` (ranged-weapon
    damage resistance kicked in)."""
    snap = await _patch_inv(
        gm_client, seraphine["id"], equipped=True, attuned=True,
    )
    flags_resp = await _ensure_auto_apply(gm_client, True)
    assert flags_resp.status_code == 200, flags_resp.text
    try:
        rowan_cid = f"tok_smt_ranged_rowan_{rowan['id']}"
        sera_cid = f"tok_smt_ranged_sera_{seraphine['id']}"
        await _seed_battle(gm_client, [
            _mkc(rowan_cid, rowan["id"], name=rowan["name"]),
            _mkc(sera_cid, seraphine["id"], name=seraphine["name"]),
        ])
        await _seed_dice(gm_client, 7)
        try:
            resp = await _attack(
                gm_client, rowan, sera_cid, ROWAN_LONGBOW_ATTACK_IDX,
            )
        finally:
            await _seed_dice(gm_client, None)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data.get("attack_name") == "Longbow"
        if not data.get("hit"):
            # Try a few seeds until a hit lands.
            for s in (1, 2, 3, 4, 5, 6, 8, 9, 10, 11):
                await _seed_dice(gm_client, s)
                try:
                    resp = await _attack(
                        gm_client, rowan, sera_cid, ROWAN_LONGBOW_ATTACK_IDX,
                    )
                finally:
                    await _seed_dice(gm_client, None)
                if resp.status_code == 200 and (resp.json() or {}).get("hit"):
                    data = resp.json()
                    break
        assert data.get("hit"), f"could not land a Longbow hit: {data!r}"
        assert data.get("target_resistance_applied") is True, (
            f"expected ranged-weapon resistance on Seraphine's shield; "
            f"got target_resistance_applied="
            f"{data.get('target_resistance_applied')!r}"
        )
    finally:
        await _ensure_auto_apply(gm_client, False)
        await _restore_inv(gm_client, seraphine["id"], snap)


async def test_melee_attack_no_resistance(gm_client, seraphine, rowan):
    """Same shield equipped+attuned → Rowan's Shortsword (melee) does NOT
    trigger resistance (the resistance is ranged-only)."""
    snap = await _patch_inv(
        gm_client, seraphine["id"], equipped=True, attuned=True,
    )
    flags_resp = await _ensure_auto_apply(gm_client, True)
    assert flags_resp.status_code == 200, flags_resp.text
    try:
        rowan_cid = f"tok_smt_melee_rowan_{rowan['id']}"
        sera_cid = f"tok_smt_melee_sera_{seraphine['id']}"
        await _seed_battle(gm_client, [
            _mkc(rowan_cid, rowan["id"], name=rowan["name"]),
            _mkc(sera_cid, seraphine["id"], name=seraphine["name"]),
        ])
        # Land a hit.
        data = None
        for s in (7, 1, 2, 3, 4, 5, 6, 8, 9, 10, 11):
            await _seed_dice(gm_client, s)
            try:
                resp = await _attack(
                    gm_client, rowan, sera_cid, ROWAN_SHORTSWORD_ATTACK_IDX,
                )
            finally:
                await _seed_dice(gm_client, None)
            if resp.status_code == 200 and (resp.json() or {}).get("hit"):
                data = resp.json()
                break
        assert data is not None, "could not land a Shortsword hit"
        assert "Shortsword" in (data.get("attack_name") or "")
        assert data.get("target_resistance_applied") is False, (
            f"melee attack should not trigger ranged-weapon resistance; "
            f"got target_resistance_applied="
            f"{data.get('target_resistance_applied')!r}"
        )
    finally:
        await _ensure_auto_apply(gm_client, False)
        await _restore_inv(gm_client, seraphine["id"], snap)


async def test_no_resistance_without_attunement(gm_client, seraphine, rowan):
    """Equipped-but-NOT-attuned → no ranged-weapon resistance fires."""
    snap = await _patch_inv(
        gm_client, seraphine["id"], equipped=True, attuned=False,
    )
    flags_resp = await _ensure_auto_apply(gm_client, True)
    assert flags_resp.status_code == 200, flags_resp.text
    try:
        rowan_cid = f"tok_smt_noatt_rowan_{rowan['id']}"
        sera_cid = f"tok_smt_noatt_sera_{seraphine['id']}"
        await _seed_battle(gm_client, [
            _mkc(rowan_cid, rowan["id"], name=rowan["name"]),
            _mkc(sera_cid, seraphine["id"], name=seraphine["name"]),
        ])
        data = None
        for s in (7, 1, 2, 3, 4, 5, 6, 8, 9, 10, 11):
            await _seed_dice(gm_client, s)
            try:
                resp = await _attack(
                    gm_client, rowan, sera_cid, ROWAN_LONGBOW_ATTACK_IDX,
                )
            finally:
                await _seed_dice(gm_client, None)
            if resp.status_code == 200 and (resp.json() or {}).get("hit"):
                data = resp.json()
                break
        assert data is not None, "could not land a Longbow hit"
        assert data.get("target_resistance_applied") is False, (
            f"unattuned shield should not grant resistance; got "
            f"target_resistance_applied="
            f"{data.get('target_resistance_applied')!r}"
        )
    finally:
        await _ensure_auto_apply(gm_client, False)
        await _restore_inv(gm_client, seraphine["id"], snap)
