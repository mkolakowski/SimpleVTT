"""v2.99.188 — Hunter's Mark Twinned: chat-card names both targets.

Closes the v2.99.187 UI follow-up. v2.99.187 wired the install
buff's rider to carry both targets (list-shape effects field) but
the `feature_used` broadcast's `feature_name` + `feature_desc`
only named the primary, so chat readers couldn't see that a
second mark was installed.

v2.99.188 extends the broadcast:
  - `feature_name` becomes "🎯 Hunter's Mark → PRIMARY + SECONDARY"
    when Twinned fires.
  - `feature_desc` mentions both targets by name.
  - New broadcast fields: `target_names` (list), `twinned_target_name`,
    `twinned_target_combatant_id_2` (already on the response too).
  - Weapon-hit rider uplift dict now carries `vs_combatant_id` so
    a downstream UI consumer can render "Hunter's Mark (vs NAME)"
    on the attack chat card without re-resolving the target.

Tests:
  - With Twinned: the install broadcast names both targets and
    surfaces the new metadata fields.
  - Without Twinned: the install broadcast keeps its single-
    target shape (backward compat).
"""
import asyncio
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _place_token(gm_client, char_id, x, y):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/place-token",
        json={"x": float(x), "y": float(y)},
    )
    assert r.status_code == 200, r.text
    return r.json()


async def _seed_battle_with_twinned(
    gm_client, caster_id, caster_name, second_target_id,
    primary_target_id, primary_target_name, primary_target_char_id,
    second_target_name="Second Target", spell_level=1,
):
    return await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_hmtb_caster_{caster_id}",
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
             "initiative": 8, "hp_current": 50, "hp_max": 50,
             "buffs": [],
             "speed_walk": 30,
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )


async def test_twinned_install_broadcast_names_both_targets(
    gm_client, gm_ws, roster,
):
    """When Twinned folds in a second target, the install
    feature_used broadcast names both targets in the name +
    description and surfaces the new metadata fields.
    """
    rowan = roster["Rowan Quickbow"]
    krieger = roster["Krieger Stonefist"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/rest",
        json={"type": "long"},
    )
    await _place_token(gm_client, krieger["id"], 400.0, 400.0)
    second_tok = "tok_hmtb_dire_wolf"
    primary_tok = f"tok_hmtb_kr_{krieger['id']}"
    await _seed_battle_with_twinned(
        gm_client, rowan["id"], rowan["name"], second_tok,
        primary_target_id=primary_tok,
        primary_target_name=krieger["name"],
        primary_target_char_id=krieger["id"],
        second_target_name="Dire Wolf",
        spell_level=1,
    )
    gm_ws.mark()
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
    await asyncio.sleep(0.2)
    feats = gm_ws.buffered("feature_used")
    hm_broadcast = next(
        (m for m in feats
         if (m.get("data") or {}).get("source") == "hunters-mark"),
        None,
    )
    assert hm_broadcast is not None, (
        "v2.99.188: expected a hunters-mark feature_used broadcast"
    )
    d = hm_broadcast["data"]
    feature_name = d.get("feature_name") or ""
    feature_desc = d.get("feature_desc") or ""
    # Primary name should be there.
    assert krieger["name"] in feature_name, (
        f"v2.99.188: primary target name should appear in feature_name; "
        f"got {feature_name!r}"
    )
    # Second target name should be there.
    assert "Dire Wolf" in feature_name, (
        f"v2.99.188: Twinned second target name should appear in "
        f"feature_name; got {feature_name!r}"
    )
    assert "Dire Wolf" in feature_desc, (
        f"v2.99.188: Twinned second target name should appear in "
        f"feature_desc; got {feature_desc!r}"
    )
    # New broadcast metadata.
    target_names = d.get("target_names") or []
    assert krieger["name"] in target_names and "Dire Wolf" in target_names, (
        f"v2.99.188: target_names should list both names; got {target_names}"
    )
    assert d.get("twinned_target_combatant_id_2") == second_tok, (
        f"v2.99.188: twinned_target_combatant_id_2 should mirror "
        f"the second target; got {d.get('twinned_target_combatant_id_2')}"
    )
    assert d.get("twinned_target_name") == "Dire Wolf", (
        f"v2.99.188: twinned_target_name should resolve to the "
        f"combatant's display name; got {d.get('twinned_target_name')!r}"
    )


async def test_no_twinned_broadcast_keeps_single_target(
    gm_client, gm_ws, roster,
):
    """Control: cast Hunter's Mark with no Twinned pending. The
    install broadcast keeps its single-target shape — primary only
    in the name/desc, no twinned_target_name set.
    """
    rowan = roster["Rowan Quickbow"]
    krieger = roster["Krieger Stonefist"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/rest",
        json={"type": "long"},
    )
    await _place_token(gm_client, krieger["id"], 400.0, 400.0)
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_hmnb_rw_{rowan['id']}",
             "char_id": rowan["id"], "name": rowan["name"],
             "initiative": 10, "hp_current": 30, "hp_max": 30,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": f"tok_hmnb_kr_{krieger['id']}",
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
        f"/api/campaign/{CAMPAIGN_ID}/cast_hunters_mark",
        json={
            "character_id": rowan["id"],
            "target_character_id": krieger["id"],
            "slot_level": 1,
            "override": True,
        },
    )
    assert cast.status_code == 200, cast.text
    await asyncio.sleep(0.2)
    feats = gm_ws.buffered("feature_used")
    hm_broadcast = next(
        (m for m in feats
         if (m.get("data") or {}).get("source") == "hunters-mark"),
        None,
    )
    assert hm_broadcast is not None
    d = hm_broadcast["data"]
    assert d.get("twinned_target_combatant_id_2") in (None, ""), (
        f"v2.99.188: no Twinned → twinned_target_combatant_id_2 "
        f"should be falsy; got {d.get('twinned_target_combatant_id_2')!r}"
    )
    assert not d.get("twinned_target_name"), (
        f"v2.99.188: no Twinned → twinned_target_name should be "
        f"falsy; got {d.get('twinned_target_name')!r}"
    )
    target_names = d.get("target_names") or []
    assert target_names == [krieger["name"]], (
        f"v2.99.188: no Twinned → target_names should be the single "
        f"primary name; got {target_names}"
    )
