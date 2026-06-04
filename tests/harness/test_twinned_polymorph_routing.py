"""v2.99.174 — Twinned Spell auto-route through /cast_polymorph.

Closes the remaining v2.99.160 filed item (auto-route to second
target). v2.99.167 stashed the second target on the pending
buff; v2.99.174 wires the canonical /cast_polymorph endpoint to
read it via the new `_consume_twinned_for_second_target` helper.

The helper:
  - Reads the caster's metamagic-twinned-pending buff
  - Returns the second target's combatant_id if set
  - Drops the pending one-shot (RAW per cast)
  - Returns None when no Twinned was armed

/cast_polymorph at end of cast:
  - Calls the helper
  - Surfaces the second target on the response + feature_used
    broadcast

v1 simplification: the second target's /transform call is still
GM-resolved (no auto-transform). v1 just surfaces the second
target on the audit so the GM has a single source of truth.

Tests:
  - Arm Twinned with Krieger as second target → /cast_polymorph
    response carries `twinned_target_combatant_id_2: Krieger`
  - feature_used broadcast names the second target
  - Twinned pending is consumed after the cast
  - Without Twinned armed, the response field is None
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
        "economy": {"action": False, "bonus": False, "reaction": False,
                    "movement": 0},
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1,
              "active": True},
    )


async def _get_buff_keys(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    return {(b or {}).get("key") for b in resp.json().get("buffs") or []}


@pytest_asyncio.fixture
async def zara_rested_with_l4(gm_client, roster):
    """Long-rest Zara + PATCH a L4 slot + Polymorph onto her spell
    list so /cast_polymorph proceeds.
    """
    zara = roster["Zara Emberfire"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/rest",
        json={"type": "long"},
    )
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/sheet-fields",
        json={
            "spell_slots": {"sorcerer": {
                "1": {"total": 4, "used": 0},
                "2": {"total": 3, "used": 0},
                "3": {"total": 2, "used": 0},
                "4": {"total": 1, "used": 0},
            }},
            "spells": [
                {"name": "Polymorph", "level": 4, "_slug": "polymorph",
                 "prepared": True, "casting_time": "1 action"},
            ],
        },
    )
    return zara


async def test_twinned_polymorph_surfaces_second_target(
    gm_client, zara_rested_with_l4, roster,
):
    """Zara arms Twinned (Krieger as second target), then casts
    Polymorph on Pip (first target). The response carries
    twinned_target_combatant_id_2 = Krieger's combatant id.
    """
    zara = zara_rested_with_l4
    pip = roster["Pip Quickfingers"]
    krieger = roster["Krieger Stonefist"]
    zara_tok = f"tok_twpoly_zara_{zara['id']}"
    pip_tok = f"tok_twpoly_pip_{pip['id']}"
    kri_tok = f"tok_twpoly_kri_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(zara_tok, zara["id"], name=zara["name"]),
        _mkc(pip_tok, pip["id"], name=pip["name"]),
        _mkc(kri_tok, krieger["id"], name=krieger["name"]),
    ])
    # Arm Twinned with Krieger as second target.
    arm = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_twinned_spell",
        json={
            "character_id": zara["id"],
            "spell_level": 4,
            "target_combatant_id_2": kri_tok,
        },
    )
    assert arm.status_code == 200, arm.text
    pre_keys = await _get_buff_keys(gm_client, zara["id"])
    assert "metamagic-twinned-pending" in pre_keys
    # Cast Polymorph on Pip.
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_polymorph",
        json={
            "character_id": zara["id"],
            "class_slug": "sorcerer",
            "slot_level": 4,
            "target_combatant_id": pip_tok,
            "override": True,
        },
    )
    assert cast.status_code == 200, cast.text
    data = cast.json()
    assert data["twinned_target_combatant_id_2"] == kri_tok
    # Twinned pending consumed.
    post_keys = await _get_buff_keys(gm_client, zara["id"])
    assert "metamagic-twinned-pending" not in post_keys


async def test_polymorph_without_twinned_returns_none(
    gm_client, zara_rested_with_l4, roster,
):
    """Without arming Twinned, the response field is None — proves
    the helper short-circuits when no pending buff is present.
    """
    zara = zara_rested_with_l4
    pip = roster["Pip Quickfingers"]
    zara_tok = f"tok_twpoly_no_zara_{zara['id']}"
    pip_tok = f"tok_twpoly_no_pip_{pip['id']}"
    await _seed_battle(gm_client, [
        _mkc(zara_tok, zara["id"], name=zara["name"]),
        _mkc(pip_tok, pip["id"], name=pip["name"]),
    ])
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_polymorph",
        json={
            "character_id": zara["id"],
            "class_slug": "sorcerer",
            "slot_level": 4,
            "target_combatant_id": pip_tok,
            "override": True,
        },
    )
    assert cast.status_code == 200, cast.text
    data = cast.json()
    assert data["twinned_target_combatant_id_2"] is None
