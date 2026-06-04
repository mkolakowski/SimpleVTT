"""v2.99.187 — Per-target install for /cast_hunters_mark Twinned.

Closes a v2.99.183 filed item. v2.99.183 wired the Twinned helper
into /cast_hunters_mark — the response surfaced
`twinned_target_combatant_id_2` but the installed Hunter's Mark
buff carried a single-target rider
(`effects.weapon_hit_bonus_target_combatant_id: <primary>`), so
the second target wasn't actually marked for the weapon-hit rider.

v2.99.187 changes the buff shape: when Twinned folds in a second
target, the rider's target field becomes a list `[primary,
secondary]` (and a new top-level `target_combatant_ids` mirrors
the same two IDs). The consumer at the weapon-hit rider
resolution path was updated to accept list-or-string, so single-
target installs still work.

Tests:
  - Cast Hunter's Mark on a primary target with Twinned armed and
    a second target seeded.
  - Verify (a) the response carries `twinned_target_combatant_id_2`,
    (b) Rowan's Hunter's Mark buff effects field carries a
    list-shape `weapon_hit_bonus_target_combatant_id` containing
    both target IDs, (c) the buff's `target_combatant_ids` mirrors
    both.
  - Control: cast Hunter's Mark without Twinned armed → the buff
    still carries the single-string shape (backward compat with
    other consumers).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _get_buffs(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    return r.json().get("buffs") or []


async def _place_token(gm_client, char_id, x, y):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/place-token",
        json={"x": float(x), "y": float(y)},
    )
    assert r.status_code == 200, r.text
    return r.json()


async def _seed_battle_with_twinned(
    gm_client, caster_id, caster_name, second_target_id, spell_level=1,
):
    return await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_hmti_caster_{caster_id}",
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


async def test_hunters_mark_twinned_installs_list_rider(
    gm_client, roster,
):
    """Rowan casts Hunter's Mark with Twinned armed + a second
    target seeded. The installed buff should carry list-shape
    rider targets covering both.
    """
    rowan = roster["Rowan Quickbow"]
    krieger = roster["Krieger Stonefist"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/rest",
        json={"type": "long"},
    )
    await _place_token(gm_client, krieger["id"], 400.0, 400.0)
    second_tok = "tok_hmti_second_target"
    await _seed_battle_with_twinned(
        gm_client, rowan["id"], rowan["name"], second_tok,
        spell_level=1,
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
    assert data["twinned_target_combatant_id_2"] == second_tok, (
        f"v2.99.187: response should surface the second target; "
        f"got {data}"
    )
    primary_tok = data["target_combatant_id"]
    # Inspect Rowan's installed Hunter's Mark buff.
    buffs = await _get_buffs(gm_client, rowan["id"])
    hm = next(
        (b for b in buffs if (b or {}).get("key") == "hunters-mark"),
        None,
    )
    assert hm is not None, (
        f"v2.99.187: hunters-mark buff should be installed on Rowan; "
        f"got {[b.get('key') for b in buffs]}"
    )
    rider = (hm.get("effects") or {}).get("weapon_hit_bonus_target_combatant_id")
    assert isinstance(rider, list), (
        f"v2.99.187: rider target should be a list when Twinned "
        f"folds in a second target; got {rider!r}"
    )
    assert primary_tok in rider, (
        f"v2.99.187: primary target should be in the list rider; "
        f"got {rider!r} (primary={primary_tok})"
    )
    assert second_tok in rider, (
        f"v2.99.187: second (Twinned) target should be in the list "
        f"rider; got {rider!r} (second={second_tok})"
    )
    all_ids = hm.get("target_combatant_ids") or []
    assert primary_tok in all_ids and second_tok in all_ids, (
        f"v2.99.187: target_combatant_ids should mirror both targets; "
        f"got {all_ids!r}"
    )


async def test_hunters_mark_no_twinned_keeps_single_rider(
    gm_client, roster,
):
    """Control: cast Hunter's Mark with no Twinned pending. The
    buff's rider target should remain a single string (backward
    compat with pre-v2.99.187 serialized buffs + with /cast_hex's
    still-singular field).
    """
    rowan = roster["Rowan Quickbow"]
    krieger = roster["Krieger Stonefist"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/rest",
        json={"type": "long"},
    )
    await _place_token(gm_client, krieger["id"], 400.0, 400.0)
    # Clean battle — no Twinned pending on Rowan.
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_hmnt_rw_{rowan['id']}",
             "char_id": rowan["id"], "name": rowan["name"],
             "initiative": 10, "hp_current": 30, "hp_max": 30,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
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
    assert not data.get("twinned_target_combatant_id_2"), (
        f"v2.99.187: no Twinned pending → response should not "
        f"surface a second target; got {data}"
    )
    primary_tok = data["target_combatant_id"]
    buffs = await _get_buffs(gm_client, rowan["id"])
    hm = next(
        (b for b in buffs if (b or {}).get("key") == "hunters-mark"),
        None,
    )
    assert hm is not None
    rider = (hm.get("effects") or {}).get("weapon_hit_bonus_target_combatant_id")
    assert rider == primary_tok, (
        f"v2.99.187: no Twinned → rider should remain a single "
        f"string equal to the primary target; got {rider!r}"
    )
