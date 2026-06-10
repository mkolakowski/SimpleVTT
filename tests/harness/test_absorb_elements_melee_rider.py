"""v2.158.49 — Absorb Elements next-melee bonus-damage rider (Phase 2).

RAW (PHB p.211, Absorb Elements): besides the resistance half (wired
in v2.158.48), the reaction grants "the first time you hit with a
melee attack on your next turn, the target takes extra [slot-level]d6
damage of the triggering type." v2.71.0 installed an
`absorb-elements-active` buff carrying `next_melee_bonus_dice` (an int
count of d6) + `next_melee_bonus_type`, but the melee-hit consumer was
deferred — the buff captured the rider for GM adjudication only.

This commit wires the rider into `_compute_attack_auto_uplifts`: on a
MELEE-WEAPON hit by the buff carrier, a `next_melee_bonus_dice`d6
uplift of `next_melee_bonus_type` is appended (source
"absorb-elements"). It is gated on `_attack_is_melee_weapon` (mirrors
Improved Divine Smite) and stamps a `once_per_turn_flag` so it fires
exactly once; the buff's 1-round duration handles overall expiry. On a
miss the once-per-turn filter strips it (no card inflation, no burn).

Test strategy (mirrors test_improved_divine_smite.py):
- happy: Sir Caelan carrying the buff swings his Longsword (melee,
  index 0) at Krieger → on a hit, auto_uplifts has an
  `absorb-elements` entry, damage_type "fire", total in [1, 6].
- control: Caelan with NO buff → no `absorb-elements` uplift.
- melee gate: Thalindra carrying the buff casts Fire Bolt (a ranged
  spell attack, not a melee weapon) → no `absorb-elements` uplift,
  proving the `_attack_is_melee_weapon` gate.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


LONGSWORD_INDEX = 0  # Sir Caelan's attacks list starts with Longsword.
FIRE_BOLT_INDEX = 1  # Thalindra's Fire Bolt (after Quarterstaff at 0).


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


def _mkc(cid, char_id=None, hp_cur=50, hp_max=75, name="X", buffs=None):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": hp_cur, "hp_max": hp_max,
        "buffs": buffs or [],
        "economy": {"action": False, "bonus": False, "reaction": False,
                    "movement": 0},
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1,
              "active": True},
    )


async def _try_attack_until_hit(
    gm_client, attacker_id, target_combatant_id, attack_index=0,
):
    """Loop attacks until one lands. Returns the auto_uplifts list
    from the first hit, or None if no hit across 15 attempts.
    """
    for _ in range(15):
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": attacker_id,
                "attack_index": attack_index,
                "target_combatant_id": target_combatant_id,
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        if data.get("hit"):
            return data.get("auto_uplifts") or []
    return None


@pytest_asyncio.fixture
async def thalindra_rested(gm_client, roster):
    thal = roster["Thalindra Moonwhisper"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thal['id']}/rest",
        json={"type": "long"},
    )
    return thal


async def test_absorb_elements_rider_fires_on_melee_hit(gm_client, roster):
    """Caelan carrying absorb-elements-active swings the Longsword at
    Krieger. On a hit, auto_uplifts should contain an `absorb-elements`
    entry with damage_type "fire" and total in [1, 6].
    """
    caelan = roster["Sir Caelan Lightbringer"]
    krieger = roster["Krieger Stonefist"]
    cae_tok = f"tok_ae_melee_cae_{caelan['id']}"
    kri_tok = f"tok_ae_melee_kri_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(cae_tok, caelan["id"], name=caelan["name"],
             buffs=[dict(_AE_BUFF)]),
        _mkc(kri_tok, krieger["id"], name=krieger["name"],
             hp_cur=50, hp_max=75),
    ])
    uplifts = await _try_attack_until_hit(
        gm_client, caelan["id"], kri_tok, attack_index=LONGSWORD_INDEX,
    )
    assert uplifts is not None, "Longsword didn't hit Krieger in 15 tries"
    ae = next(
        (u for u in uplifts if u.get("source") == "absorb-elements"),
        None,
    )
    assert ae is not None, (
        f"expected absorb-elements uplift on melee weapon hit; "
        f"got uplifts={uplifts}"
    )
    assert ae.get("damage_type") == "fire", ae
    total = int(ae.get("total") or 0)
    assert 1 <= total <= 6, f"1d6 total out of range: {ae}"


async def test_absorb_elements_rider_skipped_without_buff(gm_client, roster):
    """Control: Caelan with NO absorb-elements buff → no
    absorb-elements uplift even on a melee weapon hit.
    """
    caelan = roster["Sir Caelan Lightbringer"]
    krieger = roster["Krieger Stonefist"]
    cae_tok = f"tok_ae_melee_nb_cae_{caelan['id']}"
    kri_tok = f"tok_ae_melee_nb_kri_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(cae_tok, caelan["id"], name=caelan["name"]),
        _mkc(kri_tok, krieger["id"], name=krieger["name"],
             hp_cur=50, hp_max=75),
    ])
    uplifts = await _try_attack_until_hit(
        gm_client, caelan["id"], kri_tok, attack_index=LONGSWORD_INDEX,
    )
    assert uplifts is not None, "Longsword didn't hit Krieger in 15 tries"
    ae = next(
        (u for u in uplifts if u.get("source") == "absorb-elements"),
        None,
    )
    assert ae is None, (
        f"no buff → should NOT fire Absorb Elements rider; got {ae!r}"
    )


async def test_absorb_elements_rider_skipped_on_ranged_spell(
    gm_client, thalindra_rested, roster,
):
    """Melee gate: Thalindra carrying the buff casts Fire Bolt (a
    ranged spell attack, not a melee weapon). The rider must NOT fire
    — `_attack_is_melee_weapon` rejects a fire-typed ranged attack.
    """
    thal = thalindra_rested
    krieger = roster["Krieger Stonefist"]
    thal_tok = f"tok_ae_ranged_thal_{thal['id']}"
    kri_tok = f"tok_ae_ranged_kri_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(thal_tok, thal["id"], name=thal["name"],
             buffs=[dict(_AE_BUFF)]),
        _mkc(kri_tok, krieger["id"], name=krieger["name"],
             hp_cur=50, hp_max=75),
    ])
    uplifts = await _try_attack_until_hit(
        gm_client, thal["id"], kri_tok, attack_index=FIRE_BOLT_INDEX,
    )
    assert uplifts is not None, "Fire Bolt didn't hit Krieger in 15 tries"
    ae = next(
        (u for u in uplifts if u.get("source") == "absorb-elements"),
        None,
    )
    assert ae is None, (
        f"Fire Bolt is not a melee weapon attack — Absorb Elements rider "
        f"should be gated out; got {ae!r}"
    )
