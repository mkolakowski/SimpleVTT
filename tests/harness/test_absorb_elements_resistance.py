"""v2.158.48 — Absorb Elements resistance read site (Phase 2).

RAW (PHB p.211, Absorb Elements): the reaction grants resistance to
the triggering damage type until the start of your next turn (and a
+slot-level d6 rider on your next melee hit). v2.71.0 wired the
reaction to install an `absorb-elements-active` buff carrying
`resistance_damage_type` + `next_melee_bonus_dice` +
`next_melee_bonus_type`, but the downstream consumers were deferred
(buff captured the effects for GM adjudication only).

This commit wires the RESISTANCE half: `_resistance_halve` now reads
the buff's single `resistance_damage_type` string (distinct from the
`resistance_to` list other buffs carry) and halves matching damage.
The buff's 1-round duration handles expiry — resistance is not
consumed. The next-melee-bonus-damage rider stays deferred.

Test strategy (mirrors test_hellish_resistance.py):
- Seed a battle with Pip (Halfling — no innate fire resistance)
  carrying the absorb-elements-active buff (resistance to fire).
  Thalindra casts Fire Bolt at Pip; PUT /battle mirrors the
  combatant buff to Pip's sheet `_buffs_active`, so the damage path
  reads it. Assert `damage_applied == rolled // 2`.
- Control: Pip with no buff → `damage_applied == rolled` (no halving).

Uncanny Dodge interaction: Pip is a Thief Rogue Lv 7, so she has
Uncanny Dodge (Rogue Lv 5) — a reaction that halves the FIRST hit
taken in a battle. That means the first hit confounds the
measurement (with the buff it's quartered: Uncanny Dodge AND
resistance both halve). We therefore do NOT reseed the battle inside
the seed loop — once the reaction is spent on the first hit, every
subsequent hit reflects buff-only resistance (or, in the control, no
reduction at all). Re-PUTting the battle each iteration would reset
the reaction economy and re-trigger Uncanny Dodge on every hit,
masking the buff's effect. HP depletes slowly across iterations but
a clean match lands within the first few hits, so no reset is needed.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


_AE_BUFF = {
    "key": "absorb-elements-active",
    "name": "🌊 Absorb Elements (fire)",
    "icon": "🌊",
    "duration_rounds": 1,
    "duration_max": 1,
    "concentration": False,
    "effects": {
        "resistance_damage_type": "fire",
        "next_melee_bonus_dice": 1,
        "next_melee_bonus_type": "fire",
    },
    "desc": "Resistance to fire damage. Next melee hit +1d6 fire.",
}


async def _seed_dice(gm_client, seed: int):
    resp = await gm_client.post(
        "/api/test/dice/seed", json={"seed": seed},
    )
    assert resp.status_code == 200, resp.text


async def _set_hp(gm_client, char_id: int, hp_current: int):
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"hp": {"current": hp_current}},
    )


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


def _tok(char, hp_current: int = 40, hp_max: int = 40, buffs=None):
    return {
        "id": f"tok_ae_{char['id']}",
        "char_id": char["id"],
        "name": char["name"],
        "initiative": 10,
        "hp_current": hp_current,
        "hp_max": hp_max,
        "buffs": buffs or [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


@pytest_asyncio.fixture
async def thalindra_rested(gm_client, roster):
    thal = roster["Thalindra Moonwhisper"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thal['id']}/rest",
        json={"type": "long"},
    )
    return thal


async def test_absorb_elements_halves_matching_type(
    gm_client, thalindra_rested, roster,
):
    """Pip carrying absorb-elements-active (resistance to fire) → a
    Fire Bolt hit is halved (floor)."""
    thal = thalindra_rested
    pip = roster["Pip Quickfingers"]
    await _set_hp(gm_client, pip["id"], 40)
    await _seed_battle(gm_client, [
        _tok(thal),
        _tok(pip, buffs=[dict(_AE_BUFF)]),
    ])
    pip_tok = f"tok_ae_{pip['id']}"
    halved = False
    for seed in range(1, 200):
        await _seed_dice(gm_client, seed)
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": thal["id"],
                "attack_index": 1,  # Fire Bolt
                "target_combatant_id": pip_tok,
                "override": True,
            },
        )
        if r.status_code != 200:
            continue
        data = r.json()
        if not data.get("hit"):
            continue
        rolled = int(data.get("damage_total") or 0)
        applied = int(data.get("damage_applied") or 0)
        if rolled < 2:
            continue
        expected = rolled // 2
        if applied == expected and applied < rolled:
            halved = True
            break
    assert halved, (
        "no Fire Bolt hit with halved damage landed in 200 seeds; "
        "Absorb Elements resistance may not be firing"
    )


async def test_absorb_elements_no_resistance_without_buff(
    gm_client, thalindra_rested, roster,
):
    """Control: Pip with no buff → Fire Bolt damage is not halved."""
    thal = thalindra_rested
    pip = roster["Pip Quickfingers"]
    await _set_hp(gm_client, pip["id"], 40)
    await _seed_battle(gm_client, [
        _tok(thal),
        _tok(pip, buffs=[]),
    ])
    pip_tok = f"tok_ae_{pip['id']}"
    no_resistance = False
    for seed in range(1, 200):
        await _seed_dice(gm_client, seed)
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": thal["id"],
                "attack_index": 1,
                "target_combatant_id": pip_tok,
                "override": True,
            },
        )
        if r.status_code != 200:
            continue
        data = r.json()
        if not data.get("hit"):
            continue
        rolled = int(data.get("damage_total") or 0)
        applied = int(data.get("damage_applied") or 0)
        if rolled < 1:
            continue
        if applied == rolled:
            no_resistance = True
            break
    assert no_resistance, (
        "no un-halved Fire Bolt hit landed at Pip in 200 seeds; "
        "resistance may be over-applying"
    )
