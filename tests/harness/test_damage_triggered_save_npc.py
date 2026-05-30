"""v2.97.66 — NPC damage-triggered repeated saves.

Companion to v2.97.65's PC-side hook. When an NPC is Frightened by a
PC's Fear cast (NPC fails the install save inline), the buff lands
with the v2.97.66 install-time stamps. When the NPC then takes
damage, ``_fire_damage_triggered_saves`` looks up the NPC's stat via
``_monster_template_to_sheet``, rolls the save, broadcasts the 🩸
roll log entry, and drops the buff on a passed save.

Test flow:
- Seed battle with Lyra (bard, Fear at index 19) + Krieger (attacker)
  + a bandit NPC.
- Lyra casts Fear at the bandit; loop until the inline NPC save fails
  and Frightened lands on the bandit (with v2.97.66 stamps).
- Krieger attacks the bandit; loop until a damaging hit lands.
- Assert a 🩸 "Damage-triggered save" broadcast fires naming the
  bandit.
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


async def test_damage_to_frightened_npc_fires_repeated_save(
    gm_client, gm_ws, roster,
):
    """Lyra frightens a bandit; Krieger damages it; assert the
    🩸 'Damage-triggered save' broadcast fires for the bandit."""
    lyra = roster["Lyra Sunstrider"]
    krieger = roster["Krieger Stonefist"]

    bandit_tmpl = await _bandit_template(gm_client)
    bandit_id = "tok_dts_npc_bandit"

    lyra_tok = f"tok_dts_npc_lyra_{lyra['id']}"
    krieger_tok = f"tok_dts_npc_krieger_{krieger['id']}"

    landed = False
    for _ in range(30):
        await _long_rest(gm_client, lyra["id"])
        await _long_rest(gm_client, krieger["id"])
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={
                "combatants": [
                    {"id": lyra_tok, "char_id": lyra["id"],
                     "name": lyra["name"], "initiative": 14,
                     "hp_current": 35, "hp_max": 35, "buffs": [],
                     "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
                    {"id": krieger_tok, "char_id": krieger["id"],
                     "name": krieger["name"], "initiative": 12,
                     "hp_current": 55, "hp_max": 55, "buffs": [],
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

        # Lyra casts Fear at the bandit (Fear at index 19).
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
        # NPC save resolves inline; on fail the buff installs. The
        # /cast_spell endpoint uses ``auto_save_buff_name`` (NOT
        # ``auto_buff_installed`` — that field is from /use_stunning_strike
        # / /use_open_hand_technique).
        data = fear_cast.json()
        if data.get("auto_save_buff_name") == "Frightened":
            landed = True
            break
        # Sometimes the NPC passes; loop again.

    assert landed, "no failed NPC Wis save in 30 tries; couldn't install Frightened"

    gm_ws.mark()
    # Krieger attacks the bandit; loop until a damaging hit lands and
    # the v2.97.66 NPC hook fires.
    fired = False
    for _ in range(20):
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": krieger["id"],
                "attack_index": 0,
                "target_combatant_id": bandit_id,
                "target_name": bandit_tmpl["name"],
                "override": True,
                "override_range": True,
            },
        )
        await asyncio.sleep(0.15)
        msgs = gm_ws.buffered("roll")
        dt_msg = next(
            (m for m in msgs
             if "Damage-triggered save" in (m.get("data") or {}).get("note", "")
             and bandit_tmpl["name"] in (m.get("data") or {}).get("note", "")),
            None,
        )
        if dt_msg is not None:
            fired = True
            break

    assert fired, (
        f"expected 🩸 'Damage-triggered save' for {bandit_tmpl['name']}; "
        f"notes={[(m.get('data') or {}).get('note') for m in gm_ws.buffered('roll')]}"
    )
