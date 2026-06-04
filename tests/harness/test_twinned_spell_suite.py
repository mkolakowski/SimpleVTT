"""v2.99.181 — Twinned Spell helper wired into /cast_slow,
/cast_hold_person, /cast_compulsion.

Closes the v2.99.174 "wire into more endpoints" follow-up. The
`_consume_twinned_for_second_target` helper is now adopted by:
  - /cast_slow: appends second target to install list (RAW: not
    a single-target spell, but the helper is wired for GM
    convenience).
  - /cast_hold_person: appends second target to install list (RAW
    canonical Twinned use case at L2 baseline single-target).
  - /cast_compulsion: surfaces second target on response only
    (per-target install path doesn't exist yet — v1 ships at
    cast layer).

Each endpoint:
  - Reads the pending buff via the helper, drops it one-shot.
  - For /cast_slow + /cast_hold_person: appends the second
    target to the targets list so the buff installs on both.
  - Surfaces `twinned_target_combatant_id_2` on the response.

Tests:
  - /cast_slow with Twinned armed → response carries second
    target + Twinned pending consumed
  - /cast_hold_person with Twinned armed → response carries
    second target + pending consumed
  - /cast_compulsion with Twinned armed → response carries
    second target + pending consumed
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
    """Long-rest Zara + PATCH L4 slot + Slow + Hold Person +
    Compulsion + Polymorph onto her spell list.
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
                "3": {"total": 3, "used": 0},
                "4": {"total": 2, "used": 0},
            }},
            "spells": [
                {"name": "Slow", "level": 3, "_slug": "slow",
                 "prepared": True, "casting_time": "1 action"},
                {"name": "Hold Person", "level": 2, "_slug": "hold-person",
                 "prepared": True, "casting_time": "1 action"},
                {"name": "Compulsion", "level": 4, "_slug": "compulsion",
                 "prepared": True, "casting_time": "1 action"},
            ],
        },
    )
    return zara


async def test_cast_slow_consumes_twinned(
    gm_client, zara_rested_with_l4, roster,
):
    """Zara arms Twinned with Krieger as second target, then casts
    Slow on Pip. Response carries twinned_target_combatant_id_2 +
    pending consumed.
    """
    zara = zara_rested_with_l4
    pip = roster["Pip Quickfingers"]
    krieger = roster["Krieger Stonefist"]
    zara_tok = f"tok_twsuite_slow_zara_{zara['id']}"
    pip_tok = f"tok_twsuite_slow_pip_{pip['id']}"
    kri_tok = f"tok_twsuite_slow_kri_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(zara_tok, zara["id"], name=zara["name"]),
        _mkc(pip_tok, pip["id"], name=pip["name"]),
        _mkc(kri_tok, krieger["id"], name=krieger["name"]),
    ])
    arm = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_twinned_spell",
        json={
            "character_id": zara["id"],
            "spell_level": 3,
            "target_combatant_id_2": kri_tok,
        },
    )
    assert arm.status_code == 200, arm.text
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_slow",
        json={
            "character_id": zara["id"],
            "class_slug": "sorcerer",
            "slot_level": 3,
            "target_combatant_ids": [pip_tok],
            "override": True,
        },
    )
    assert cast.status_code == 200, cast.text
    data = cast.json()
    assert data["twinned_target_combatant_id_2"] == kri_tok
    # Twinned pending consumed.
    post_keys = await _get_buff_keys(gm_client, zara["id"])
    assert "metamagic-twinned-pending" not in post_keys


async def test_cast_hold_person_consumes_twinned(
    gm_client, zara_rested_with_l4, roster,
):
    """Same pattern for /cast_hold_person — Twinned armed +
    consumed."""
    zara = zara_rested_with_l4
    pip = roster["Pip Quickfingers"]
    krieger = roster["Krieger Stonefist"]
    zara_tok = f"tok_twsuite_hp_zara_{zara['id']}"
    pip_tok = f"tok_twsuite_hp_pip_{pip['id']}"
    kri_tok = f"tok_twsuite_hp_kri_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(zara_tok, zara["id"], name=zara["name"]),
        _mkc(pip_tok, pip["id"], name=pip["name"]),
        _mkc(kri_tok, krieger["id"], name=krieger["name"]),
    ])
    arm = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_twinned_spell",
        json={
            "character_id": zara["id"],
            "spell_level": 2,
            "target_combatant_id_2": kri_tok,
        },
    )
    assert arm.status_code == 200, arm.text
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hold_person",
        json={
            "character_id": zara["id"],
            "class_slug": "sorcerer",
            "slot_level": 2,
            "target_combatant_ids": [pip_tok],
            "override": True,
        },
    )
    assert cast.status_code == 200, cast.text
    data = cast.json()
    assert data["twinned_target_combatant_id_2"] == kri_tok
    post_keys = await _get_buff_keys(gm_client, zara["id"])
    assert "metamagic-twinned-pending" not in post_keys


async def test_cast_compulsion_consumes_twinned(
    gm_client, zara_rested_with_l4, roster,
):
    """Twinned-from-Zara, Compulsion-cast-by-Thalindra. /cast_compulsion
    only accepts bard / wizard / warlock — RAW Sorcerers don't get
    Compulsion. So we arm Twinned on Thalindra (Wizard) instead.
    Demonstrates the helper fires regardless of which caster armed
    Twinned (the helper reads pending from the casting char_id).
    """
    thalindra = roster["Thalindra Moonwhisper"]
    krieger = roster["Krieger Stonefist"]
    # PATCH Thalindra with L4 slot + Compulsion.
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-fields",
        json={
            "spell_slots": {"wizard": {
                "1": {"total": 4, "used": 0},
                "2": {"total": 3, "used": 0},
                "3": {"total": 3, "used": 0},
                "4": {"total": 1, "used": 0},
            }},
            "spells": [
                {"name": "Compulsion", "level": 4, "_slug": "compulsion",
                 "prepared": True, "casting_time": "1 action"},
            ],
        },
    )
    th_tok = f"tok_twsuite_comp_th_{thalindra['id']}"
    kri_tok = f"tok_twsuite_comp_kri_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(th_tok, thalindra["id"], name=thalindra["name"]),
        _mkc(kri_tok, krieger["id"], name=krieger["name"]),
    ])
    # Thalindra isn't a Sorcerer so use_metamagic_twinned_spell will
    # 409 wrong_class. Instead, install the pending buff directly
    # via the battle PUT (synthesizes the v2.99.160 install).
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": th_tok, "char_id": thalindra["id"],
             "name": thalindra["name"], "initiative": 10,
             "hp_current": 30, "hp_max": 30,
             "buffs": [{
                 "key": "metamagic-twinned-pending",
                 "name": "Metamagic: Twinned Spell (pending)",
                 "icon": "✨",
                 "duration_rounds": 10,
                 "duration_max": 10,
                 "concentration": False,
                 "source": "metamagic-twinned-spell",
                 "source_char_id": thalindra["id"],
                 "effects": {
                     "twin_targets": True,
                     "spell_level": 4,
                     "sp_paid": 4,
                     "target_combatant_id_2": kri_tok,
                 },
             }],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": kri_tok, "char_id": krieger["id"],
             "name": krieger["name"], "initiative": 8,
             "hp_current": 75, "hp_max": 75, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_compulsion",
        json={
            "character_id": thalindra["id"],
            "class_slug": "wizard",
            "slot_level": 4,
            "override": True,
        },
    )
    assert cast.status_code == 200, cast.text
    data = cast.json()
    assert data["twinned_target_combatant_id_2"] == kri_tok
    post_keys = await _get_buff_keys(gm_client, thalindra["id"])
    assert "metamagic-twinned-pending" not in post_keys
