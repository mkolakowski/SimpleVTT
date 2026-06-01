"""v2.99.18 — (D) Phase 3 third-ship: Tiefling Hellish Resistance.

RAW (PHB p.43, Tiefling race trait): "You have resistance to fire
damage." Fire damage taken by a Tiefling is halved (floor).

Implementation extends `_resistance_halve` to read a sheet-level
`damage_resistances` list. The field shape matches NPC monster
templates (a list of damage-type strings stored at sheet root).
Zara Emberfire's demo sheet gains `damage_resistances: ["fire"]`.
PCs with race traits granting permanent resistance populate this
list; the same code path NPCs use now serves PCs too.

Test strategy:
- Thalindra casts Fire Bolt at Zara. Damage applied should be the
  rolled total halved (floor).
- Loop seeded dice until a hit lands; compute expected_applied =
  rolled_damage // 2 and assert `damage_applied` matches the
  halved value.
- Control: Thalindra casts Fire Bolt at Pip (Halfling — no fire
  resistance). damage_applied should equal the rolled damage
  (no halving). Regression guard against over-broad resistance
  matching.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _seed_dice(gm_client, seed: int):
    resp = await gm_client.post(
        "/api/test/dice/seed", json={"seed": seed},
    )
    assert resp.status_code == 200, resp.text


async def _set_hp(gm_client, char_id: int, hp_current: int):
    """Set the character's HP via sheet-fields PATCH."""
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"hp": {"current": hp_current}},
    )


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


def _tok(char, hp_current: int = 30, hp_max: int = 60):
    return {
        "id": f"tok_hr_{char['id']}",
        "char_id": char["id"],
        "name": char["name"],
        "initiative": 10,
        "hp_current": hp_current,
        "hp_max": hp_max,
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
    }


@pytest_asyncio.fixture
async def thalindra_rested(gm_client, roster):
    thal = roster["Thalindra Moonwhisper"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thal['id']}/rest",
        json={"type": "long"},
    )
    return thal


@pytest_asyncio.fixture
async def zara_rested(gm_client, roster):
    zara = roster["Zara Emberfire"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/rest",
        json={"type": "long"},
    )
    return zara


async def test_tiefling_halves_fire_damage(
    gm_client, gm_ws, thalindra_rested, zara_rested,
):
    """Thalindra casts Fire Bolt at Zara (Tiefling Sorcerer). The
    damage rolls 2d10; after Hellish Resistance halves it, the
    `damage_applied` on the attack response should equal floor of
    half the rolled total.
    """
    thal = thalindra_rested
    zara = zara_rested
    # Reset Zara to full HP so the damage application has headroom.
    await _set_hp(gm_client, zara["id"], 37)
    await _seed_battle(gm_client, [
        _tok(thal),
        _tok(zara, hp_current=37, hp_max=37),
    ])
    zara_tok = f"tok_hr_{zara['id']}"
    # Thalindra Fire Bolt is attack index 1 (after Quarterstaff at 0).
    halved = False
    for seed in range(1, 200):
        await _seed_dice(gm_client, seed)
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": thal["id"],
                "attack_index": 1,  # Fire Bolt
                "target_combatant_id": zara_tok,
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
            continue  # need some damage to halve
        expected = rolled // 2
        if applied == expected and applied < rolled:
            halved = True
            break
    assert halved, (
        f"no Fire Bolt hit with halved damage landed in 200 seeds; "
        f"Hellish Resistance may not be firing"
    )


async def test_no_resistance_for_non_tiefling(
    gm_client, gm_ws, thalindra_rested, roster,
):
    """Control: Thalindra casts Fire Bolt at Pip (Halfling — no fire
    resistance). damage_applied should equal damage_rolled (no
    halving). Regression guard against over-broad resistance match.
    """
    thal = thalindra_rested
    pip = roster["Pip Quickfingers"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/rest",
        json={"type": "long"},
    )
    await _set_hp(gm_client, pip["id"], 40)
    await _seed_battle(gm_client, [
        _tok(thal),
        _tok(pip, hp_current=40, hp_max=40),
    ])
    pip_tok = f"tok_hr_{pip['id']}"
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
        f"no Fire Bolt hit without halving landed at Pip in 200 seeds; "
        f"resistance may be over-applying to non-Tieflings"
    )
