"""Magic Weapon — Cleric/Wizard L2, Phase 4 rider/bonus-scaling consumer.

v2.421.0 — first consumer of the rider/bonus family. RAW PHB p.257: a
nonmagical weapon gains a +1 bonus to attack and damage rolls; "when you
cast this spell using a spell slot of 4th level or higher, the bonus
increases to +2. When you use a spell slot of 6th level or higher, the
bonus increases to +3." The bonus climbs in non-linear steps, so the
endpoint reads the tier-walk substrate (`_SPELL_BONUS_MAP` via
`_spell_bonus_for_slot()`):

  - L2 → +1   (base)
  - L3 → +1   (same tier)
  - L4 → +2   (middle tier)
  - L5 → +2   (same tier)
  - L6 → +3   (top tier)
  - L9 → +3   (top tier, fallback)

The cast installs a Magic Weapon buff on the target (caster by default,
or `target_character_id`) carrying scaled `weapon_attack_bonus` /
`weapon_damage_bonus` effects — so the buff must land in an active
battle. The endpoint gates on knowing Magic Weapon OR being a Cleric /
Wizard.

Caster fixtures: Brother Tavik Stonebrow (Cleric) and Thalindra
Moonwhisper (Wizard) for the gate; Krieger Stonefist (Barbarian) for the
409 path.

Tests:
  - L2 base → +1, buff installed with +1 effects
  - L4 → +2 (middle tier)
  - L6 → +3 (top tier)
  - Wizard caster (Thalindra) → also passes the gate
  - 409 cannot_cast for a non-caster non-knower (Krieger Barbarian)
"""
from .conftest import CAMPAIGN_ID


def _pc_cb(c):
    return {
        "id": f"tok_mw_{c['id']}", "char_id": c["id"], "name": c["name"],
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
    """Fetch the persisted battle and return the magic-weapon buff dict on
    the combatant matching ``char_id`` (or None)."""
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/battle")
    assert r.status_code == 200, r.text
    state = r.json().get("battle") or {}
    for c in state.get("combatants") or []:
        if c.get("char_id") == char_id:
            for b in c.get("buffs") or []:
                if b.get("key") == "magic-weapon":
                    return b
    return None


async def test_magic_weapon_base_slot_plus1(gm_client, roster):
    """Tavik casts at L2 base → +1 bonus, buff installed with +1 effects."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _seed_active_battle(gm_client, [_pc_cb(tavik)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_magic_weapon",
        json={"character_id": tavik["id"], "slot_level": 2},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["feature"] == "magic-weapon"
    assert body["slot_level"] == 2
    assert body["bonus"] == 1
    assert body["buff_installed"] is True
    assert body["target_character_id"] == tavik["id"]
    buff = await _buff_on(gm_client, tavik["id"])
    assert buff is not None
    assert buff["effects"]["weapon_attack_bonus"] == 1
    assert buff["effects"]["weapon_damage_bonus"] == 1
    assert buff["concentration"] is False


async def test_magic_weapon_l4_plus2(gm_client, roster):
    """L4 → +2 (the middle tier)."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _seed_active_battle(gm_client, [_pc_cb(tavik)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_magic_weapon",
        json={"character_id": tavik["id"], "slot_level": 4},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["slot_level"] == 4
    assert body["bonus"] == 2
    buff = await _buff_on(gm_client, tavik["id"])
    assert buff is not None
    assert buff["effects"]["weapon_attack_bonus"] == 2
    assert buff["effects"]["weapon_damage_bonus"] == 2


async def test_magic_weapon_l6_plus3(gm_client, roster):
    """L6 → +3 (the top tier)."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _seed_active_battle(gm_client, [_pc_cb(tavik)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_magic_weapon",
        json={"character_id": tavik["id"], "slot_level": 6},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["slot_level"] == 6
    assert body["bonus"] == 3
    buff = await _buff_on(gm_client, tavik["id"])
    assert buff is not None
    assert buff["effects"]["weapon_attack_bonus"] == 3


async def test_magic_weapon_wizard_caster_passes_gate(gm_client, roster):
    """Thalindra (Wizard) isn't a Cleric but Wizard is in the caster set →
    the cast succeeds."""
    thalindra = roster["Thalindra Moonwhisper"]
    await _seed_active_battle(gm_client, [_pc_cb(thalindra)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_magic_weapon",
        json={"character_id": thalindra["id"], "slot_level": 2},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["bonus"] == 1
    assert body["buff_installed"] is True


async def test_magic_weapon_cannot_cast_non_caster(gm_client, roster):
    """Krieger (Barbarian) doesn't know the spell and isn't a Cleric/Wizard
    → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _seed_active_battle(gm_client, [_pc_cb(krieger)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_magic_weapon",
        json={"character_id": krieger["id"], "slot_level": 2},
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body.get("error") == "cannot_cast"
    assert "cleric" in body.get("expected", "").lower()
