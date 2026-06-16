"""v2.365.0 — magic-items: Arrow-Catching Shield (RAW DMG p.152, rare,
attunement). Bucket-B conditional-AC passive on the new
`conditional_ac_bonus_vs_ranged` substrate. RAW: "You gain a +2 bonus
to AC against ranged attacks while you wield this shield."

Folded into `_equipped_item_effects` + read by `_read_target_ac` when
called with `is_ranged_attack=True`. Both /attack and /npc_attack
compute the is_ranged flag from the attack's `range` string (via
`_attack_is_ranged_weapon`) and thread it through.

Demo fixture: Sir Caelan Lightbringer carries an Arrow-Catching Shield
as inert Armory's Remainder loot (line 6930 in `demo_seed.py`). The
harness PATCHes inventory equipped+attuned and uses Rowan Quickbow's
Longbow (a true ranged attack, range "150/600 ft") as the attacker.
The control case asserts the +2 only applies to ranged attacks (a
melee Longsword swing from Caelan's existing PCs does NOT pick up
the bonus).

Tests:
  - Ranged attack against an Arrow-Catching Shield wearer hits the
    target AC + 2 (the bonus surfaces in the response's `target_ac`).
  - Melee attack against the same wearer hits the base target AC
    (no conditional bonus applied).
  - Equipped-but-unattuned → no bonus on either attack type
    (attunement gate).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


_SLUG = "arrow-catching-shield"
ROWAN_LONGBOW_ATTACK_IDX = 0
CAELAN_LONGSWORD_ATTACK_IDX = 0  # melee


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
    assert found, "Caelan has no arrow-catching-shield inventory item"
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
async def caelan(roster):
    return roster["Sir Caelan Lightbringer"]


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
        },
    )


async def _baseline_ac(gm_client, caelan):
    """Caelan's base AC from /sheet-json (seed = 18 chain mail + shield)."""
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/sheet-json",
    )
    return int(((r.json() or {}).get("sheet") or {}).get("ac") or 18)


async def test_ranged_attack_adds_plus_2_ac(gm_client, caelan, rowan):
    """Arrow-Catching Shield equipped+attuned → Rowan's Longbow attack
    against Caelan sees `target_ac` = baseline + 2."""
    snap = await _patch_inv(
        gm_client, caelan["id"], equipped=True, attuned=True,
    )
    try:
        base_ac = await _baseline_ac(gm_client, caelan)
        rowan_cid = f"tok_acs_ranged_rowan_{rowan['id']}"
        caelan_cid = f"tok_acs_ranged_caelan_{caelan['id']}"
        await _seed_battle(gm_client, [
            _mkc(rowan_cid, rowan["id"], name=rowan["name"]),
            _mkc(caelan_cid, caelan["id"], name=caelan["name"]),
        ])
        await _seed_dice(gm_client, 7)
        try:
            resp = await _attack(
                gm_client, rowan, caelan_cid, ROWAN_LONGBOW_ATTACK_IDX,
            )
        finally:
            await _seed_dice(gm_client, None)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data.get("attack_name") == "Longbow"
        assert int(data.get("target_ac") or 0) == base_ac + 2, (
            f"expected target_ac={base_ac + 2} (base {base_ac} + 2 shield); "
            f"got {data.get('target_ac')!r}"
        )
    finally:
        await _restore_inv(gm_client, caelan["id"], snap)


async def test_melee_attack_no_bonus(gm_client, caelan, rowan):
    """Same shield equipped+attuned → a MELEE attack sees `target_ac`
    at the baseline (no conditional +2). Rowan's Shortsword (range
    "5 ft") is the melee fixture."""
    snap = await _patch_inv(
        gm_client, caelan["id"], equipped=True, attuned=True,
    )
    try:
        base_ac = await _baseline_ac(gm_client, caelan)
        rowan_cid = f"tok_acs_melee_rowan_{rowan['id']}"
        caelan_cid = f"tok_acs_melee_caelan_{caelan['id']}"
        await _seed_battle(gm_client, [
            _mkc(rowan_cid, rowan["id"], name=rowan["name"]),
            _mkc(caelan_cid, caelan["id"], name=caelan["name"]),
        ])
        # Rowan's attack_index 1 is a 5-ft Shortsword (melee). Verify
        # via the response.attack_name.
        await _seed_dice(gm_client, 7)
        try:
            resp = await _attack(gm_client, rowan, caelan_cid, 1)
        finally:
            await _seed_dice(gm_client, None)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "Shortsword" in (data.get("attack_name") or ""), (
            f"expected a melee Shortsword for this test fixture; got "
            f"{data.get('attack_name')!r}"
        )
        assert int(data.get("target_ac") or 0) == base_ac, (
            f"expected target_ac={base_ac} (baseline, no +2 for melee); "
            f"got {data.get('target_ac')!r}"
        )
    finally:
        await _restore_inv(gm_client, caelan["id"], snap)


async def test_no_bonus_without_attunement(gm_client, caelan, rowan):
    """Equipped-but-NOT-attuned shield → no +2 even on a ranged attack
    (attunement gate)."""
    snap = await _patch_inv(
        gm_client, caelan["id"], equipped=True, attuned=False,
    )
    try:
        base_ac = await _baseline_ac(gm_client, caelan)
        rowan_cid = f"tok_acs_noatt_rowan_{rowan['id']}"
        caelan_cid = f"tok_acs_noatt_caelan_{caelan['id']}"
        await _seed_battle(gm_client, [
            _mkc(rowan_cid, rowan["id"], name=rowan["name"]),
            _mkc(caelan_cid, caelan["id"], name=caelan["name"]),
        ])
        await _seed_dice(gm_client, 7)
        try:
            resp = await _attack(
                gm_client, rowan, caelan_cid, ROWAN_LONGBOW_ATTACK_IDX,
            )
        finally:
            await _seed_dice(gm_client, None)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert int(data.get("target_ac") or 0) == base_ac, (
            f"expected target_ac={base_ac} (baseline, no +2 unattuned); "
            f"got {data.get('target_ac')!r}"
        )
    finally:
        await _restore_inv(gm_client, caelan["id"], snap)
