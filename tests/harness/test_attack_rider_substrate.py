"""v2.99.395 — Phase 2.1: on-hit rider substrate (full-feature-automation).

Exercises the extended `_compute_attack_auto_uplifts` buff-rider block
(docs/plans/on-hit-riders.md) directly, by installing synthetic rider
buffs on the attacker combatant via PUT /battle and asserting they
surface in the /attack response's `auto_uplifts`:

  - `weapon_hit_bonus_flat` — flat bonus rider (target-keyed).
  - flat rider with NO stored target — self/"this-turn" rider applies
    to any hit.
  - `weapon_hit_bonus_dice` + `weapon_hit_bonus_flat` combined.
  - `weapon_hit_once_per_turn` gating — pre-set economy flag suppresses
    the rider.
  - v2.99.400 (Phase 2.4): `weapon_hit_convert_type` re-types the whole
    hit's damage in the weapon_attack broadcast (asserted via gm_ws,
    since the conversion lands on damage_type, not in auto_uplifts).

Plain (non-once-per-turn) riders are NOT stripped on a miss, so these
assertions are deterministic regardless of the random attack roll.
AC 1 on the dummy guarantees the hit where a confirmed hit is needed
(the conversion only applies on a hit).

Pip Quickfingers (Rogue, Shortsword = attack_index 0, piercing) is the
attacker; a synthetic NPC dummy is the target.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _mkc(cid, char_id=None, name="X", buffs=None, economy=None, ac=None):
    c = {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": 50, "hp_max": 50,
        "buffs": buffs or [],
        "speed_walk": 30,
        "economy": economy or {"action": False, "bonus": False,
                               "reaction": False, "movement": 0},
    }
    if ac is not None:
        c["ac"] = ac
    return c


async def _seed_battle(gm_client, combatants):
    return await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


@pytest_asyncio.fixture
async def pip_rested(gm_client, roster):
    pip = roster["Pip Quickfingers"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/rest",
        json={"type": "long"},
    )
    return pip


def _uplift(data, source):
    return [u for u in (data.get("auto_uplifts") or [])
            if u.get("source") == source]


async def test_flat_rider_target_keyed(gm_client, pip_rested, roster):
    """A buff with weapon_hit_bonus_flat keyed to the target adds a flat
    uplift of the right amount + damage type."""
    pip = pip_rested
    pip_cid = f"tok_rs1_pip_{pip['id']}"
    dummy_cid = "tok_rs1_dummy"
    buff = {
        "key": "test-flat-rider", "name": "Test Flat Rider",
        "effects": {
            "weapon_hit_bonus_flat": 4,
            "weapon_hit_bonus_target_combatant_id": dummy_cid,
            "weapon_hit_bonus_damage_type": "necrotic",
        },
    }
    await _seed_battle(gm_client, [
        _mkc(pip_cid, pip["id"], name=pip["name"], buffs=[buff]),
        _mkc(dummy_cid, None, name="Dummy", ac=1),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={"character_id": pip["id"], "attack_index": 0,
              "target_combatant_id": dummy_cid, "override": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    ups = _uplift(data, "test-flat-rider")
    assert len(ups) == 1, data.get("auto_uplifts")
    assert ups[0]["total"] == 4
    assert ups[0]["expression"] == "+4"
    assert ups[0]["damage_type"] == "necrotic"


async def test_flat_rider_no_target_applies_to_any(gm_client, pip_rested):
    """A flat rider buff with NO stored target (self/this-turn rider)
    applies to any hit."""
    pip = pip_rested
    pip_cid = f"tok_rs2_pip_{pip['id']}"
    dummy_cid = "tok_rs2_dummy"
    buff = {
        "key": "test-selfrider", "name": "Test Self Rider",
        "effects": {"weapon_hit_bonus_flat": 3,
                    "weapon_hit_bonus_damage_type": "radiant"},
    }
    await _seed_battle(gm_client, [
        _mkc(pip_cid, pip["id"], name="Pip", buffs=[buff]),
        _mkc(dummy_cid, None, name="Dummy", ac=1),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={"character_id": pip["id"], "attack_index": 0,
              "target_combatant_id": dummy_cid, "override": True},
    )
    assert resp.status_code == 200, resp.text
    ups = _uplift(resp.json(), "test-selfrider")
    assert len(ups) == 1
    assert ups[0]["total"] == 3
    assert ups[0]["damage_type"] == "radiant"


async def test_dice_plus_flat_rider(gm_client, pip_rested):
    """A rider with both dice and flat sums them (expression 1d6+2)."""
    pip = pip_rested
    pip_cid = f"tok_rs3_pip_{pip['id']}"
    dummy_cid = "tok_rs3_dummy"
    buff = {
        "key": "test-dice-flat", "name": "Test Dice+Flat",
        "effects": {
            "weapon_hit_bonus_dice": "1d6",
            "weapon_hit_bonus_flat": 2,
            "weapon_hit_bonus_target_combatant_id": dummy_cid,
        },
    }
    await _seed_battle(gm_client, [
        _mkc(pip_cid, pip["id"], name="Pip", buffs=[buff]),
        _mkc(dummy_cid, None, name="Dummy", ac=1),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={"character_id": pip["id"], "attack_index": 0,
              "target_combatant_id": dummy_cid, "override": True},
    )
    assert resp.status_code == 200, resp.text
    ups = _uplift(resp.json(), "test-dice-flat")
    assert len(ups) == 1
    assert ups[0]["expression"] == "1d6+2"
    assert 3 <= ups[0]["total"] <= 8  # 1d6 (1-6) + 2


async def test_once_per_turn_flag_suppresses_rider(gm_client, pip_rested):
    """A once-per-turn rider whose economy.<flag>_used is already set does
    NOT fire (gated out before the hit/miss check)."""
    pip = pip_rested
    pip_cid = f"tok_rs4_pip_{pip['id']}"
    dummy_cid = "tok_rs4_dummy"
    buff = {
        "key": "test-opt-rider", "name": "Test Once-Per-Turn",
        "effects": {
            "weapon_hit_bonus_flat": 5,
            "weapon_hit_once_per_turn": True,
            "weapon_hit_flag": "testopt",
            "weapon_hit_bonus_target_combatant_id": dummy_cid,
        },
    }
    # Pre-set the once-per-turn flag so the rider is already spent.
    econ = {"action": False, "bonus": False, "reaction": False,
            "movement": 0, "testopt_used": True}
    await _seed_battle(gm_client, [
        _mkc(pip_cid, pip["id"], name="Pip", buffs=[buff], economy=econ),
        _mkc(dummy_cid, None, name="Dummy", ac=1),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={"character_id": pip["id"], "attack_index": 0,
              "target_combatant_id": dummy_cid, "override": True},
    )
    assert resp.status_code == 200, resp.text
    ups = _uplift(resp.json(), "test-opt-rider")
    assert ups == [], "spent once-per-turn rider should not fire"


async def test_convert_type_retypes_hit_damage(gm_client, pip_rested):
    """v2.99.400 — Phase 2.4: a buff with weapon_hit_convert_type re-types
    the whole hit's damage. Pip's Shortsword is piercing; the rider keyed
    to the target converts it to force on a confirmed hit. The conversion
    fires only on a hit, so retry until a swing connects (this rider is
    NOT once-per-turn, so it converts every hit)."""
    pip = pip_rested
    pip_cid = f"tok_rs5_pip_{pip['id']}"
    dummy_cid = "tok_rs5_dummy"
    buff = {
        "key": "test-convert-rider", "name": "Test Convert Rider",
        "effects": {
            "weapon_hit_convert_type": "force",
            "weapon_hit_bonus_target_combatant_id": dummy_cid,
        },
    }
    await _seed_battle(gm_client, [
        _mkc(pip_cid, pip["id"], name=pip["name"], buffs=[buff]),
        _mkc(dummy_cid, None, name="Dummy"),
    ])
    hit_data = None
    for _ in range(12):
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={"character_id": pip["id"], "attack_index": 0,
                  "target_combatant_id": dummy_cid, "override": True},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        if data["hit"]:
            hit_data = data
            break
    assert hit_data is not None, "expected at least one hit in 12 swings"
    assert hit_data["damage_type"] == "force", hit_data
