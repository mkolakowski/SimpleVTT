"""Elemental Weapon — Ranger/Paladin L3, Phase 4 rider/bonus-scaling
second consumer.

v2.422.0 — the second rider/bonus consumer, and the first to scale *two*
riders off one tier value. RAW PHB p.237: a nonmagical weapon gains a +1
bonus to attack rolls and deals an extra 1d4 damage of a chosen element;
"when you cast this spell using a spell slot of 5th or 6th level, the
bonus increases to +2 and the extra damage increases to 2d4. When you use
a spell slot of 7th level or higher, the bonus increases to +3 and the
extra damage increases to 3d4." The single tier-walk value N (read from
`_SPELL_BONUS_MAP` via `_spell_bonus_for_slot()`) drives both `+N` attack
and `Nd4` damage:

  - L3 → +1 / 1d4   (base)
  - L4 → +1 / 1d4   (same tier)
  - L5 → +2 / 2d4   (middle tier)
  - L7 → +3 / 3d4   (top tier)

Unlike Magic Weapon (one rider, non-concentration), Elemental Weapon is
**concentration** and carries an element choice (default fire). The cast
installs the buff on the target — so it needs an active battle.

Caster fixtures: Rowan Quickbow (Ranger) for the ladder, Sir Caelan
Lightbringer (Paladin) for the gate; Krieger Stonefist (Barbarian) for
the 409 path.

Tests:
  - L3 base → +1 / 1d4 fire, buff installed with matching effects
  - L5 → +2 / 2d4 (middle tier)
  - L7 → +3 / 3d4 (top tier), explicit cold element
  - Paladin caster (Sir Caelan) → also passes the gate
  - 409 cannot_cast for a non-caster non-knower (Krieger Barbarian)
"""
from .conftest import CAMPAIGN_ID


def _pc_cb(c):
    return {
        "id": f"tok_ew_{c['id']}", "char_id": c["id"], "name": c["name"],
        "initiative": 10, "hp_current": 40, "hp_max": 40, "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _seed_active_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


async def _buff_on(gm_client, char_id):
    """Fetch the persisted battle and return the elemental-weapon buff dict
    on the combatant matching ``char_id`` (or None)."""
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/battle")
    assert r.status_code == 200, r.text
    state = r.json().get("battle") or {}
    for c in state.get("combatants") or []:
        if c.get("char_id") == char_id:
            for b in c.get("buffs") or []:
                if b.get("key") == "elemental-weapon":
                    return b
    return None


async def test_elemental_weapon_base_slot_plus1_1d4(gm_client, roster):
    """Rowan casts at L3 base → +1 / 1d4 fire, buff installed with matching
    effects (and concentration True)."""
    rowan = roster["Rowan Quickbow"]
    await _seed_active_battle(gm_client, [_pc_cb(rowan)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_elemental_weapon",
        json={"character_id": rowan["id"], "slot_level": 3},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["feature"] == "elemental-weapon"
    assert body["slot_level"] == 3
    assert body["bonus"] == 1
    assert body["bonus_dice"] == "1d4"
    assert body["damage_type"] == "fire"
    assert body["buff_installed"] is True
    assert body["target_character_id"] == rowan["id"]
    buff = await _buff_on(gm_client, rowan["id"])
    assert buff is not None
    assert buff["effects"]["weapon_attack_bonus"] == 1
    assert buff["effects"]["weapon_bonus_damage_dice"] == "1d4"
    assert buff["effects"]["weapon_bonus_damage_type"] == "fire"
    assert buff["concentration"] is True


async def test_elemental_weapon_l5_plus2_2d4(gm_client, roster):
    """L5 → +2 / 2d4 (middle tier)."""
    rowan = roster["Rowan Quickbow"]
    await _seed_active_battle(gm_client, [_pc_cb(rowan)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_elemental_weapon",
        json={"character_id": rowan["id"], "slot_level": 5},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["slot_level"] == 5
    assert body["bonus"] == 2
    assert body["bonus_dice"] == "2d4"
    buff = await _buff_on(gm_client, rowan["id"])
    assert buff is not None
    assert buff["effects"]["weapon_attack_bonus"] == 2
    assert buff["effects"]["weapon_bonus_damage_dice"] == "2d4"


async def test_elemental_weapon_l7_plus3_3d4_cold(gm_client, roster):
    """L7 → +3 / 3d4 (top tier); an explicit cold element is honored."""
    rowan = roster["Rowan Quickbow"]
    await _seed_active_battle(gm_client, [_pc_cb(rowan)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_elemental_weapon",
        json={"character_id": rowan["id"], "slot_level": 7,
              "damage_type": "cold"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["slot_level"] == 7
    assert body["bonus"] == 3
    assert body["bonus_dice"] == "3d4"
    assert body["damage_type"] == "cold"
    buff = await _buff_on(gm_client, rowan["id"])
    assert buff is not None
    assert buff["effects"]["weapon_attack_bonus"] == 3
    assert buff["effects"]["weapon_bonus_damage_dice"] == "3d4"
    assert buff["effects"]["weapon_bonus_damage_type"] == "cold"


async def test_elemental_weapon_paladin_caster_passes_gate(gm_client, roster):
    """Sir Caelan (Paladin) isn't a Ranger but Paladin is in the caster set
    → the cast succeeds."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _seed_active_battle(gm_client, [_pc_cb(caelan)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_elemental_weapon",
        json={"character_id": caelan["id"], "slot_level": 3},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["bonus"] == 1
    assert body["buff_installed"] is True


async def test_elemental_weapon_cannot_cast_non_caster(gm_client, roster):
    """Krieger (Barbarian) doesn't know the spell and isn't a
    Ranger/Paladin → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _seed_active_battle(gm_client, [_pc_cb(krieger)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_elemental_weapon",
        json={"character_id": krieger["id"], "slot_level": 3},
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body.get("error") == "cannot_cast"
    assert "ranger" in body.get("expected", "").lower()
