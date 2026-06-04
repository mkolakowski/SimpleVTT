"""v2.99.183 — Twinned Spell helper wired into 4 more cast endpoints.

Closes the v2.99.181 "more endpoints" follow-up. The
`_consume_twinned_for_second_target` helper is now adopted by:
  - /cast_hunters_mark (Ranger Lv 1 bonus action)
  - /cast_hex (Warlock Lv 1 bonus action)
  - /cast_bestow_curse (L3 touch concentration)
  - /cast_bane (L1 30 ft up to 3 targets)

Each endpoint:
  - Reads the pending buff via the helper after the
    concentration anchor / buff install.
  - Drops the pending one-shot.
  - Surfaces `twinned_target_combatant_id_2` on the response.

For all 4 endpoints: per-target buff install on the second
target is filed. v1 ships the cast-layer Twinned hook only.

Tests:
  - All 4 endpoints surface the second target on the response
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
    gm_client, caster_id, caster_name, caster_class_slug,
    second_target_id, spell_level=4,
):
    """Synthesize the caster + Twinned pending + Krieger as the
    second target. Bypasses /use_metamagic_twinned_spell so the
    test can wire Twinned for non-Sorcerer casters too.
    """
    return await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_{caster_class_slug}_caster_{caster_id}",
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
        ], "turn_index": 0, "round": 1, "active": True},
    )


@pytest_asyncio.fixture
async def thalindra_rested(gm_client, roster):
    """Long-rest Thalindra so resources are fresh."""
    thalindra = roster["Thalindra Moonwhisper"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/rest",
        json={"type": "long"},
    )
    return thalindra


async def test_cast_bestow_curse_consumes_twinned(
    gm_client, thalindra_rested, roster,
):
    """Thalindra casts Bestow Curse with Twinned armed → response
    carries twinned_target_combatant_id_2.
    """
    thalindra = thalindra_rested
    # PATCH Thalindra with L3 slot + Bestow Curse on her spell list.
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-fields",
        json={
            "spell_slots": {"wizard": {
                "1": {"total": 4, "used": 0},
                "2": {"total": 3, "used": 0},
                "3": {"total": 3, "used": 0},
            }},
            "spells": [
                {"name": "Bestow Curse", "level": 3,
                 "_slug": "bestow-curse", "prepared": True,
                 "casting_time": "1 action"},
            ],
        },
    )
    second_tok = f"tok_bc_twin_target_thalindra"
    await _seed_battle_with_twinned(
        gm_client, thalindra["id"], thalindra["name"], "wizard",
        second_tok, spell_level=3,
    )
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_bestow_curse",
        json={
            "character_id": thalindra["id"],
            "class_slug": "wizard",
            "slot_level": 3,
            "override": True,
        },
    )
    assert cast.status_code == 200, cast.text
    data = cast.json()
    assert data["twinned_target_combatant_id_2"] == second_tok


async def test_cast_bane_consumes_twinned(
    gm_client, roster,
):
    """Brother Tavik (Cleric) casts Bane with Twinned armed."""
    tavik = roster["Brother Tavik Stonebrow"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/rest",
        json={"type": "long"},
    )
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/sheet-fields",
        json={"spells": [
            {"name": "Bane", "level": 1, "_slug": "bane",
             "prepared": True, "casting_time": "1 action"},
        ]},
    )
    second_tok = f"tok_bn_twin_target_tavik"
    await _seed_battle_with_twinned(
        gm_client, tavik["id"], tavik["name"], "cleric",
        second_tok, spell_level=1,
    )
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_bane",
        json={
            "character_id": tavik["id"],
            "class_slug": "cleric",
            "slot_level": 1,
            "override": True,
        },
    )
    assert cast.status_code == 200, cast.text
    data = cast.json()
    assert data["twinned_target_combatant_id_2"] == second_tok


async def test_cast_hex_consumes_twinned(
    gm_client, roster,
):
    """Magnus (Warlock) casts Hex with Twinned armed."""
    magnus = roster["Magnus Hexbinder"]
    krieger = roster["Krieger Stonefist"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )
    second_tok = f"tok_hex_twin_target_magnus"
    await _seed_battle_with_twinned(
        gm_client, magnus["id"], magnus["name"], "warlock",
        second_tok, spell_level=3,
    )
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hex",
        json={
            "character_id": magnus["id"],
            "target_character_id": krieger["id"],
            "ability": "STR",
            "slot_level": 3,
            "override": True,
        },
    )
    assert cast.status_code == 200, cast.text
    data = cast.json()
    assert data["twinned_target_combatant_id_2"] == second_tok


async def test_cast_hunters_mark_consumes_twinned(
    gm_client, roster,
):
    """Rowan (Ranger) casts Hunter's Mark with Twinned armed."""
    rowan = roster["Rowan Quickbow"]
    krieger = roster["Krieger Stonefist"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/rest",
        json={"type": "long"},
    )
    second_tok = f"tok_hm_twin_target_rowan"
    await _seed_battle_with_twinned(
        gm_client, rowan["id"], rowan["name"], "ranger",
        second_tok, spell_level=1,
    )
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hunters_mark",
        json={
            "character_id": rowan["id"],
            "target_character_id": krieger["id"],
            "slot_level": 1,
            "override": True,
        },
    )
    assert cast.status_code == 200, cast.text
    data = cast.json()
    assert data["twinned_target_combatant_id_2"] == second_tok
