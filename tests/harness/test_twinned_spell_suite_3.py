"""v2.99.184 — Twinned Spell helper wired into final 3 cast endpoints.

Closes the v2.99.183 "finish coverage" follow-up. The
`_consume_twinned_for_second_target` helper is now adopted by:
  - /cast_flesh_to_stone (L6 staged Restrained → Petrified)
  - /cast_hold_monster (L5 Paralyzed, base single + upcast +1)
  - /cast_sleep (HP-pool sphere — wired for consistency, not RAW
    Twinned-valid but the GM can decline)

Each endpoint:
  - Reads the pending buff via the helper.
  - Drops the pending one-shot.
  - For /cast_hold_monster + /cast_sleep: appends second target
    to install/affected list.
  - For /cast_flesh_to_stone: surfaces on response only (per-
    target stage-flag routing is filed).

The Twinned auto-route helper is now adopted across 11 of the 11
shipped cast endpoints.

Tests:
  - All 3 endpoints surface the second target on the response
    when Twinned is armed.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _mkc(cid, char_id=None, name="X"):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": 50, "hp_max": 50,
        "buffs": [],
        "speed_walk": 30,
        "economy": {"action": False, "bonus": False, "reaction": False,
                    "movement": 0},
    }


async def _seed_battle_with_twinned(
    gm_client, caster_id, caster_name,
    second_target_id, spell_level=4,
    extra_combatants=None,
):
    """Battle with the caster (armed Twinned pending) + second target
    + any additional combatants the caller needs.
    """
    combatants = [
        {"id": f"tok_twfinal_caster_{caster_id}",
         "char_id": caster_id, "name": caster_name,
         "initiative": 10, "hp_current": 30, "hp_max": 30,
         "buffs": [{
             "key": "metamagic-twinned-pending",
             "name": "Metamagic: Twinned Spell (pending)",
             "icon": "✨",
             "duration_rounds": 10,
             "duration_max": 10,
             "concentration": False,
             "source": "metamagic-twinned-spell",
             "source_char_id": caster_id,
             "effects": {
                 "twin_targets": True,
                 "spell_level": spell_level,
                 "sp_paid": spell_level,
                 "target_combatant_id_2": second_target_id,
             },
         }],
         "economy": {"action": False, "bonus": False,
                     "reaction": False, "movement": 0}},
        {"id": second_target_id, "char_id": None,
         "name": "Twin Target",
         "initiative": 8, "hp_current": 50, "hp_max": 50,
         "buffs": [],
         "speed_walk": 30,
         "economy": {"action": False, "bonus": False,
                     "reaction": False, "movement": 0}},
    ]
    if extra_combatants:
        combatants.extend(extra_combatants)
    return await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1,
              "active": True},
    )


@pytest_asyncio.fixture
async def thalindra_with_l6_slot(gm_client, roster):
    thalindra = roster["Thalindra Moonwhisper"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/rest",
        json={"type": "long"},
    )
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-fields",
        json={
            "spell_slots": {"wizard": {
                "1": {"total": 4, "used": 0},
                "2": {"total": 3, "used": 0},
                "3": {"total": 3, "used": 0},
                "4": {"total": 1, "used": 0},
                "5": {"total": 1, "used": 0},
                "6": {"total": 1, "used": 0},
            }},
            "spells": [
                {"name": "Flesh to Stone", "level": 6,
                 "_slug": "flesh-to-stone", "prepared": True},
                {"name": "Hold Monster", "level": 5,
                 "_slug": "hold-monster", "prepared": True},
                {"name": "Sleep", "level": 1, "_slug": "sleep",
                 "prepared": True},
            ],
        },
    )
    return thalindra


async def test_cast_flesh_to_stone_consumes_twinned(
    gm_client, thalindra_with_l6_slot,
):
    """Flesh to Stone with Twinned → response carries second target."""
    thalindra = thalindra_with_l6_slot
    second_tok = "tok_fts_twin_target"
    await _seed_battle_with_twinned(
        gm_client, thalindra["id"], thalindra["name"],
        second_tok, spell_level=6,
    )
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_flesh_to_stone",
        json={
            "character_id": thalindra["id"],
            "class_slug": "wizard",
            "slot_level": 6,
            "target_combatant_id": second_tok,
            "override": True,
        },
    )
    assert cast.status_code == 200, cast.text
    data = cast.json()
    assert data["twinned_target_combatant_id_2"] == second_tok


async def test_cast_hold_monster_consumes_twinned(
    gm_client, thalindra_with_l6_slot,
):
    """Hold Monster with Twinned → response carries second target."""
    thalindra = thalindra_with_l6_slot
    primary_tok = "tok_hm2_primary"
    second_tok = "tok_hm2_twin"
    await _seed_battle_with_twinned(
        gm_client, thalindra["id"], thalindra["name"],
        second_tok, spell_level=5,
        extra_combatants=[
            {"id": primary_tok, "char_id": None, "name": "Primary",
             "initiative": 5, "hp_current": 50, "hp_max": 50,
             "buffs": [], "speed_walk": 30,
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ],
    )
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hold_monster",
        json={
            "character_id": thalindra["id"],
            "class_slug": "wizard",
            "slot_level": 5,
            "target_combatant_ids": [primary_tok],
            "override": True,
        },
    )
    assert cast.status_code == 200, cast.text
    data = cast.json()
    assert data["twinned_target_combatant_id_2"] == second_tok


async def test_cast_sleep_consumes_twinned(
    gm_client, thalindra_with_l6_slot,
):
    """Sleep with Twinned → response carries second target. RAW
    Sleep isn't a single-target spell (Twinned doesn't apply); the
    helper is wired for consistency.
    """
    thalindra = thalindra_with_l6_slot
    primary_tok = "tok_sleep_primary"
    second_tok = "tok_sleep_twin"
    await _seed_battle_with_twinned(
        gm_client, thalindra["id"], thalindra["name"],
        second_tok, spell_level=1,
        extra_combatants=[
            {"id": primary_tok, "char_id": None, "name": "Primary",
             "initiative": 5, "hp_current": 5, "hp_max": 5,
             "buffs": [], "speed_walk": 30,
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ],
    )
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_sleep",
        json={
            "character_id": thalindra["id"],
            "class_slug": "wizard",
            "slot_level": 1,
            "target_combatant_ids": [primary_tok],
            "override": True,
        },
    )
    assert cast.status_code == 200, cast.text
    data = cast.json()
    assert data["twinned_target_combatant_id_2"] == second_tok
