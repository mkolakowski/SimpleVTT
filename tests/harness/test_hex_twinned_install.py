"""v2.99.189 — Per-target install + chat-card naming for /cast_hex Twinned.

Closes the v2.99.187/.188 Hex follow-up. v2.99.187 wired Hunter's
Mark with a list-shape rider + new top-level `target_combatant_ids`
field; v2.99.188 extended the install broadcast to name both
targets. v2.99.189 applies the same pattern to /cast_hex (Warlock
L1 bonus action with the same effect-dict shape).

The shared weapon-hit rider consumer at line ~21498 already
accepts list-or-string (v2.99.187), so /cast_hex just needed the
install + broadcast changes:
  - Move `_consume_twinned_for_second_target` call BEFORE the buff
    is built.
  - Install the buff with a list-shape rider when Twinned fires.
  - Surface `target_combatant_ids` on the buff.
  - Extend install broadcast: `feature_name` + `feature_desc`
    name both targets; new metadata fields `target_names`,
    `twinned_target_combatant_id_2`, `twinned_target_name`.

Tests:
  - With Twinned: buff carries list-shape rider + both targets in
    `target_combatant_ids`; install broadcast names both targets.
  - Without Twinned: buff keeps single-string rider; broadcast
    keeps single-target shape (backward compat).
"""
import asyncio
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
    gm_client, caster_id, caster_name,
    primary_target_id, primary_target_name, primary_target_char_id,
    second_target_id, second_target_name="Cursed Cultist",
    spell_level=1,
):
    return await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_hxti_caster_{caster_id}",
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
            {"id": primary_target_id, "char_id": primary_target_char_id,
             "name": primary_target_name,
             "initiative": 9, "hp_current": 75, "hp_max": 75,
             "buffs": [],
             "speed_walk": 30,
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": second_target_id, "char_id": None,
             "name": second_target_name,
             "initiative": 8, "hp_current": 30, "hp_max": 30,
             "buffs": [],
             "speed_walk": 30,
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )


async def test_hex_twinned_install_list_rider_and_broadcast(
    gm_client, gm_ws, roster,
):
    """Magnus (Warlock) casts Hex with Twinned armed + a second
    target seeded. The installed buff carries a list-shape rider
    + both targets in `target_combatant_ids`; the install
    broadcast names both targets.
    """
    magnus = roster["Magnus Hexbinder"]
    krieger = roster["Krieger Stonefist"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )
    await _place_token(gm_client, krieger["id"], 400.0, 400.0)
    primary_tok = f"tok_hxti_kr_{krieger['id']}"
    second_tok = "tok_hxti_cultist"
    await _seed_battle_with_twinned(
        gm_client, magnus["id"], magnus["name"],
        primary_target_id=primary_tok,
        primary_target_name=krieger["name"],
        primary_target_char_id=krieger["id"],
        second_target_id=second_tok,
        second_target_name="Cursed Cultist",
        spell_level=1,
    )
    gm_ws.mark()
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hex",
        json={
            "character_id": magnus["id"],
            "target_character_id": krieger["id"],
            "slot_level": 1,
            "ability": "STR",
            "override": True,
        },
    )
    assert cast.status_code == 200, cast.text
    data = cast.json()
    assert data["twinned_target_combatant_id_2"] == second_tok, (
        f"v2.99.189: response should surface second target; got {data}"
    )
    # Inspect Magnus's installed Hex buff.
    buffs = await _get_buffs(gm_client, magnus["id"])
    hex_buff = next(
        (b for b in buffs if (b or {}).get("key") == "hex"),
        None,
    )
    assert hex_buff is not None, (
        f"v2.99.189: hex buff should be installed; got "
        f"{[b.get('key') for b in buffs]}"
    )
    rider = (hex_buff.get("effects") or {}).get(
        "weapon_hit_bonus_target_combatant_id"
    )
    assert isinstance(rider, list), (
        f"v2.99.189: rider should be list when Twinned fires; got {rider!r}"
    )
    assert primary_tok in rider and second_tok in rider, (
        f"v2.99.189: both targets in rider; got {rider!r}"
    )
    all_ids = hex_buff.get("target_combatant_ids") or []
    assert primary_tok in all_ids and second_tok in all_ids, (
        f"v2.99.189: both targets in target_combatant_ids; got {all_ids!r}"
    )
    # Broadcast names both.
    await asyncio.sleep(0.2)
    feats = gm_ws.buffered("feature_used")
    hex_broadcast = next(
        (m for m in feats if (m.get("data") or {}).get("source") == "hex"),
        None,
    )
    assert hex_broadcast is not None
    d = hex_broadcast["data"]
    feature_name = d.get("feature_name") or ""
    feature_desc = d.get("feature_desc") or ""
    assert krieger["name"] in feature_name and "Cursed Cultist" in feature_name, (
        f"v2.99.189: both target names in feature_name; got {feature_name!r}"
    )
    assert "Cursed Cultist" in feature_desc, (
        f"v2.99.189: second target name in feature_desc; got {feature_desc!r}"
    )
    target_names = d.get("target_names") or []
    assert krieger["name"] in target_names and "Cursed Cultist" in target_names, (
        f"v2.99.189: target_names lists both; got {target_names}"
    )
    assert d.get("twinned_target_combatant_id_2") == second_tok
    assert d.get("twinned_target_name") == "Cursed Cultist"


async def test_hex_no_twinned_keeps_single_target(
    gm_client, gm_ws, roster,
):
    """Control: Magnus casts Hex without Twinned. Buff keeps
    single-string rider; broadcast keeps single-target shape.
    """
    magnus = roster["Magnus Hexbinder"]
    krieger = roster["Krieger Stonefist"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )
    await _place_token(gm_client, krieger["id"], 400.0, 400.0)
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_hxnt_mg_{magnus['id']}",
             "char_id": magnus["id"], "name": magnus["name"],
             "initiative": 10, "hp_current": 30, "hp_max": 30,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": f"tok_hxnt_kr_{krieger['id']}",
             "char_id": krieger["id"], "name": krieger["name"],
             "initiative": 9, "hp_current": 75, "hp_max": 75,
             "buffs": [],
             "speed_walk": 30,
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    gm_ws.mark()
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hex",
        json={
            "character_id": magnus["id"],
            "target_character_id": krieger["id"],
            "slot_level": 1,
            "ability": "STR",
            "override": True,
        },
    )
    assert cast.status_code == 200, cast.text
    data = cast.json()
    assert not data.get("twinned_target_combatant_id_2"), (
        f"v2.99.189: no Twinned → no second target in response; got {data}"
    )
    primary_tok = data["target_combatant_id"]
    buffs = await _get_buffs(gm_client, magnus["id"])
    hex_buff = next(
        (b for b in buffs if (b or {}).get("key") == "hex"),
        None,
    )
    assert hex_buff is not None
    rider = (hex_buff.get("effects") or {}).get(
        "weapon_hit_bonus_target_combatant_id"
    )
    assert rider == primary_tok, (
        f"v2.99.189: no Twinned → rider keeps single-string shape; "
        f"got {rider!r}"
    )
    await asyncio.sleep(0.2)
    feats = gm_ws.buffered("feature_used")
    hex_broadcast = next(
        (m for m in feats if (m.get("data") or {}).get("source") == "hex"),
        None,
    )
    assert hex_broadcast is not None
    d = hex_broadcast["data"]
    target_names = d.get("target_names") or []
    assert target_names == [krieger["name"]], (
        f"v2.99.189: no Twinned → target_names is singleton; got {target_names}"
    )
    assert not d.get("twinned_target_name")
    assert not d.get("twinned_target_combatant_id_2")
