"""v2.99.208 — Diamond Soul (Monk Lv 14+).

Phase F.2 start of the v2.99.193 phased completion plan. RAW
PHB p.79: "Beginning at 14th level, your mastery of ki grants
you proficiency in all saving throws. Additionally, whenever
you make a saving throw and fail, you can spend 1 ki point to
reroll it and take the second result."

v1 ships part 1 (proficiency in all saves). Part 2 (ki-spend
reroll) is filed for a follow-up endpoint mirroring v2.99.199
/use_indomitable_reroll.

Wired the same way as v2.99.206 Slippery Mind: gate
cast_polymorph's unwilling-target WIS save mod calc to OR
`saving_throws.WIS` with `_pc_has_diamond_soul`. Kael Brightleaf
(Way of the Open Hand Monk Lv 7 default) is the demo fixture.

Tests:
  - Happy: Kael at Lv 14 vs Polymorph unwilling → save_mod
    includes proficiency.
  - Control: Kael at Lv 7 (default) vs Polymorph → save_mod
    smaller than at Lv 14.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _seed_dice(gm_client, seed: int):
    r = await gm_client.post(
        "/api/test/dice/seed", json={"seed": seed},
    )
    assert r.status_code == 200, r.text


async def _patch_sheet(gm_client, char_id, fields, class_slug=None):
    body = dict(fields)
    if class_slug:
        body["class_slug"] = class_slug
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json=body,
    )
    assert r.status_code == 200, r.text


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


def _tok(char):
    return {
        "id": f"tok_ds_{char['id']}",
        "char_id": char["id"],
        "name": char["name"],
        "initiative": 10,
        "hp_current": 30, "hp_max": 30,
        "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _seed_thalindra_with_polymorph(gm_client, thalindra):
    stock_slots = {
        "1": {"total": 4, "used": 0},
        "2": {"total": 3, "used": 0},
        "3": {"total": 3, "used": 0},
        "4": {"total": 1, "used": 0},
    }
    await _patch_sheet(
        gm_client, thalindra["id"],
        {
            "spell_slots": {"wizard": stock_slots},
            "spells": [
                {"name": "Polymorph", "level": 4, "_slug": "polymorph",
                 "prepared": True, "casting_time": "1 action"},
            ],
        },
        class_slug="wizard",
    )


async def _cast_polymorph(gm_client, thalindra, target_combatant_id):
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_polymorph",
        json={
            "character_id": thalindra["id"],
            "class_slug": "wizard",
            "slot_level": 4,
            "target_combatant_id": target_combatant_id,
            "unwilling": True,
            "override": True,
        },
    )


async def test_diamond_soul_grants_save_proficiency_at_lv14(
    gm_client, roster,
):
    """Kael at Lv 7 vs Polymorph WIS save → baseline save_total.
    Kael at Lv 14 → save_total higher (Diamond Soul adds prof).
    """
    kael = roster["Kael Brightleaf"]
    thalindra = roster["Thalindra Moonwhisper"]
    await _seed_thalindra_with_polymorph(gm_client, thalindra)
    kael_tok = f"tok_ds_{kael['id']}"
    # Baseline at Lv 7.
    await _seed_battle(gm_client, [_tok(thalindra), _tok(kael)])
    await _seed_dice(gm_client, 200)
    r = await _cast_polymorph(gm_client, thalindra, kael_tok)
    assert r.status_code == 200, r.text
    data_lv7 = r.json()
    total_lv7 = data_lv7["save_total"]
    # Bump to Lv 14.
    pre_level = 7
    await _patch_sheet(
        gm_client, kael["id"], {"level": 14},
        class_slug="monk",
    )
    try:
        await _seed_thalindra_with_polymorph(gm_client, thalindra)
        await _seed_battle(gm_client, [_tok(thalindra), _tok(kael)])
        await _seed_dice(gm_client, 200)
        r = await _cast_polymorph(gm_client, thalindra, kael_tok)
        assert r.status_code == 200, r.text
        data_lv14 = r.json()
        total_lv14 = data_lv14["save_total"]
        assert total_lv14 > total_lv7, (
            f"v2.99.208: Diamond Soul at Lv 14 should add "
            f"proficiency to WIS save; got Lv7 total={total_lv7}, "
            f"Lv14 total={total_lv14}"
        )
    finally:
        await _patch_sheet(
            gm_client, kael["id"], {"level": pre_level},
            class_slug="monk",
        )
