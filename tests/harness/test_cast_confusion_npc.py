"""v2.97.72 — Thalindra casts Confusion at a bandit via /cast_spell.

Closes the loop: the actual /cast_spell flow exercises the path that
v2.97.71 (catalog entries) + v2.97.70 (helper) + v2.97.62/69 (end-
of-turn auto-fire) built up. Thalindra is now Lv 7 wizard with L4
spell slots; Confusion is at spell_index 12.

Test flow:
- Seed battle with Thalindra + a bandit NPC.
- Thalindra casts Confusion at the bandit (slot_level 4).
- Loop until bandit fails the inline Wis save → Confused installs
  with v2.97.71 stamps + v2.97.66 NPC install plumbing.
- Advance the turn from bandit (turn 1) to Thalindra (turn 0, round 2)
  → bandit's turn just ended.
- Assert a 🔁 End-of-turn save broadcast fires for the bandit.
"""
import asyncio

from .conftest import CAMPAIGN_ID


async def _long_rest(gm_client, char_id: int) -> None:
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )
    assert resp.status_code == 200, resp.text


async def _bandit_template(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    return next(
        (t for t in templates if "bandit" in t["name"].lower()),
        templates[0],
    )


async def test_thalindra_casts_confusion_on_bandit_npc(
    gm_client, gm_ws, roster,
):
    """Thalindra casts Confusion at a bandit; bandit fails inline
    Wis save; advance turn; assert 🔁 End-of-turn save broadcast
    fires for the bandit."""
    thal = roster["Thalindra Moonwhisper"]

    bandit_tmpl = await _bandit_template(gm_client)
    bandit_id = "tok_conf_bandit"
    thal_tok = f"tok_conf_thal_{thal['id']}"

    landed = False
    for _ in range(30):
        await _long_rest(gm_client, thal["id"])
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={
                "combatants": [
                    {"id": thal_tok, "char_id": thal["id"],
                     "name": thal["name"], "initiative": 14,
                     "hp_current": 37, "hp_max": 37, "buffs": [],
                     "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
                    {"id": bandit_id, "char_id": None,
                     "token_template_id": bandit_tmpl["id"],
                     "name": bandit_tmpl["name"], "initiative": 7,
                     "hp_current": 30, "hp_max": 30, "buffs": [],
                     "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
                ],
                "turn_index": 0, "round": 1, "active": True,
            },
        )

        # Thalindra casts Confusion (spell_index 12, L4 slot).
        cast = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": thal["id"],
                "spell_index": 12,
                "slot_level": 4,
                "class_slug": "wizard",
                "target_combatant_id": bandit_id,
                "target_name": bandit_tmpl["name"],
                "override": True,
                "override_range": True,
            },
        )
        assert cast.status_code == 200, cast.text
        data = cast.json()
        if data.get("auto_save_buff_name") == "Confused":
            landed = True
            break

    assert landed, "no failed bandit Wis save in 30 tries; Confused didn't install"

    # Advance turn from bandit (turn 1) → Thalindra (turn 0, round 2).
    # Start by setting turn_index = 1 (bandit's slot).
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [
                {"id": thal_tok, "char_id": thal["id"],
                 "name": thal["name"], "initiative": 14,
                 "hp_current": 37, "hp_max": 37, "buffs": [],
                 "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
                {"id": bandit_id, "char_id": None,
                 "token_template_id": bandit_tmpl["id"],
                 "name": bandit_tmpl["name"], "initiative": 7,
                 "hp_current": 30, "hp_max": 30,
                 "buffs": [
                     {"key": "confused", "name": "Confused",
                      "icon": "🌀",
                      "duration_rounds": 10, "duration_max": 10,
                      "concentration": False,
                      "source_char_id": thal["id"],
                      "source_char_name": thal["name"],
                      "source_spell": "Confusion",
                      "effects": [],
                      "repeated_save_ability": "WIS",
                      "repeated_save_dc": 14,
                      "source_caster_creature_type": "",
                      "save_on_damage": False}
                 ],
                 "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
            ],
            "turn_index": 1, "round": 1, "active": True,
        },
    )

    gm_ws.mark()
    # End bandit's turn → advance to Thalindra (turn 0, round 2).
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [
                {"id": thal_tok, "char_id": thal["id"],
                 "name": thal["name"], "initiative": 14,
                 "hp_current": 37, "hp_max": 37, "buffs": [],
                 "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
                {"id": bandit_id, "char_id": None,
                 "token_template_id": bandit_tmpl["id"],
                 "name": bandit_tmpl["name"], "initiative": 7,
                 "hp_current": 30, "hp_max": 30,
                 "buffs": [
                     {"key": "confused", "name": "Confused",
                      "icon": "🌀",
                      "duration_rounds": 10, "duration_max": 10,
                      "concentration": False,
                      "source_char_id": thal["id"],
                      "source_char_name": thal["name"],
                      "source_spell": "Confusion",
                      "effects": [],
                      "repeated_save_ability": "WIS",
                      "repeated_save_dc": 14,
                      "source_caster_creature_type": "",
                      "save_on_damage": False}
                 ],
                 "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
            ],
            "turn_index": 0, "round": 2, "active": True,
        },
    )

    await asyncio.sleep(0.3)
    roll_msgs = gm_ws.buffered("roll")
    eot_msg = next(
        (m for m in roll_msgs
         if "End-of-turn save" in (m.get("data") or {}).get("note", "")
         and "Confused" in (m.get("data") or {}).get("note", "")
         and bandit_tmpl["name"] in (m.get("data") or {}).get("note", "")),
        None,
    )
    assert eot_msg is not None, (
        f"expected 🔁 'End-of-turn save' for {bandit_tmpl['name']}'s "
        f"Confused buff; got "
        f"notes={[(m.get('data') or {}).get('note') for m in roll_msgs]}"
    )
