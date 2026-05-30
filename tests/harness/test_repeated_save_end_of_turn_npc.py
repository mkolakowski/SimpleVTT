"""v2.97.69 — NPC end-of-turn auto-fire saves.

Companion to v2.97.62's PC-side hook. When an NPC is Frightened by a
PC's Fear cast (NPC fails the install save inline), the buff lands
with the v2.97.66 install-time stamps. When the turn advances away
from the NPC, PUT /battle's v2.97.69 hook walks the NPC's buffs,
builds the save modifier via ``_monster_template_to_sheet``, rolls
the save, broadcasts the 🔁 roll log entry, and drops the buff on
pass.

Test flow:
- Seed battle with Lyra + a bandit at turns 0 and 1.
- Lyra casts Fear at the bandit; loop until Frightened lands.
- PUT /battle advances turn from bandit (turn 1) to Lyra (turn 0,
  round 2) — bandit's turn just ended.
- Assert a 🔁 "End-of-turn save" broadcast fires naming the bandit.
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


async def test_end_of_turn_auto_fires_for_frightened_npc(
    gm_client, gm_ws, roster,
):
    """Lyra frightens a bandit; turn advances away from the bandit;
    assert the 🔁 End-of-turn save broadcast fires for the bandit."""
    lyra = roster["Lyra Sunstrider"]

    bandit_tmpl = await _bandit_template(gm_client)
    bandit_id = "tok_eot_npc_bandit"
    lyra_tok = f"tok_eot_npc_lyra_{lyra['id']}"

    landed = False
    for _ in range(30):
        await _long_rest(gm_client, lyra["id"])
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={
                "combatants": [
                    {"id": lyra_tok, "char_id": lyra["id"],
                     "name": lyra["name"], "initiative": 14,
                     "hp_current": 35, "hp_max": 35, "buffs": [],
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

        fear_cast = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": lyra["id"],
                "spell_index": 19,
                "slot_level": 3,
                "class_slug": "bard",
                "target_combatant_id": bandit_id,
                "target_name": bandit_tmpl["name"],
                "override": True,
                "override_range": True,
            },
        )
        assert fear_cast.status_code == 200, fear_cast.text
        data = fear_cast.json()
        if data.get("auto_save_buff_name") == "Frightened":
            landed = True
            break

    assert landed, "no failed NPC Wis save in 30 tries; couldn't install Frightened"

    # Advance turn from bandit (turn 1) to Lyra (turn 0, round 2).
    # That requires the bandit being the active combatant first. Set
    # turn_index=1, then advance to 0/round 2 — bandit's turn ends.
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [
                {"id": lyra_tok, "char_id": lyra["id"],
                 "name": lyra["name"], "initiative": 14,
                 "hp_current": 35, "hp_max": 35, "buffs": [],
                 "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
                {"id": bandit_id, "char_id": None,
                 "token_template_id": bandit_tmpl["id"],
                 "name": bandit_tmpl["name"], "initiative": 7,
                 "hp_current": 30, "hp_max": 30,
                 "buffs": [
                     {"key": "frightened", "name": "Frightened",
                      "icon": "😱",
                      "duration_rounds": 10, "duration_max": 10,
                      "concentration": False,
                      "source_char_id": lyra["id"],
                      "source_char_name": lyra["name"],
                      "source_spell": "Fear",
                      "effects": [],
                      "repeated_save_ability": "WIS",
                      "repeated_save_dc": 14,
                      "source_caster_creature_type": "",
                      "save_on_damage": True}
                 ],
                 "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
            ],
            "turn_index": 1, "round": 1, "active": True,
        },
    )

    gm_ws.mark()
    # End the bandit's turn → advance to Lyra (turn 0, round 2).
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [
                {"id": lyra_tok, "char_id": lyra["id"],
                 "name": lyra["name"], "initiative": 14,
                 "hp_current": 35, "hp_max": 35, "buffs": [],
                 "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
                {"id": bandit_id, "char_id": None,
                 "token_template_id": bandit_tmpl["id"],
                 "name": bandit_tmpl["name"], "initiative": 7,
                 "hp_current": 30, "hp_max": 30,
                 "buffs": [
                     {"key": "frightened", "name": "Frightened",
                      "icon": "😱",
                      "duration_rounds": 10, "duration_max": 10,
                      "concentration": False,
                      "source_char_id": lyra["id"],
                      "source_char_name": lyra["name"],
                      "source_spell": "Fear",
                      "effects": [],
                      "repeated_save_ability": "WIS",
                      "repeated_save_dc": 14,
                      "source_caster_creature_type": "",
                      "save_on_damage": True}
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
         and bandit_tmpl["name"] in (m.get("data") or {}).get("note", "")),
        None,
    )
    assert eot_msg is not None, (
        f"expected 🔁 'End-of-turn save' for {bandit_tmpl['name']}; "
        f"notes={[(m.get('data') or {}).get('note') for m in roll_msgs]}"
    )
