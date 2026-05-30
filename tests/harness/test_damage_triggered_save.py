"""v2.97.65 — damage-triggered repeated saves for Fear + Hideous Laughter.

RAW Fear (PHB p.240): "At the end of each of its turns, AND EACH
TIME IT TAKES DAMAGE, the target can make another Wisdom saving
throw." v2.97.62 covers the end-of-turn case; v2.97.65 wires the
damage-trigger case via a new ``_fire_damage_triggered_saves``
helper in ``_apply_damage_to_combatant``'s PC branch.

Test flow:
- Seed battle with Lyra (creature_type="fiend" override), Krieger,
  and Pip.
- Lyra casts Fear at Pip; loop until Pip fails the install save
  and Frightened lands (with the v2.97.65 ``save_on_damage`` stamp).
- Confirm the buff carries the marker.
- Krieger attacks Pip; the v2.97.65 hook should fire as soon as
  damage applies.
- Assert a 🩸 "Damage-triggered save" broadcast fires for Pip.
"""
import asyncio

from .conftest import CAMPAIGN_ID


async def _long_rest(gm_client, char_id: int) -> None:
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )
    assert resp.status_code == 200, resp.text


async def test_damage_to_frightened_pc_fires_repeated_save(
    gm_client, gm_ws, roster,
):
    """Lyra frightens Pip; Krieger deals damage; assert a
    'Damage-triggered save' broadcast fires."""
    lyra = roster["Lyra Sunstrider"]
    krieger = roster["Krieger Stonefist"]
    pip = roster["Pip Quickfingers"]

    lyra_tok = f"tok_dts_lyra_{lyra['id']}"
    krieger_tok = f"tok_dts_krieger_{krieger['id']}"
    pip_tok = f"tok_dts_pip_{pip['id']}"

    landed = False
    for _ in range(30):
        await _long_rest(gm_client, lyra["id"])
        await _long_rest(gm_client, krieger["id"])
        await _long_rest(gm_client, pip["id"])
        for _stale in (
            "frightened", "paralyzed", "charmed", "baned", "faerie-fired",
            "protection-from-evil-and-good", "heroism", "bless",
        ):
            await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/end_buff",
                json={"character_id": pip["id"], "key": _stale},
            )

        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={
                "combatants": [
                    {"id": lyra_tok, "char_id": lyra["id"],
                     "name": lyra["name"], "initiative": 14,
                     "hp_current": 35, "hp_max": 35, "buffs": [],
                     "creature_type": "fiend",
                     "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
                    {"id": krieger_tok, "char_id": krieger["id"],
                     "name": krieger["name"], "initiative": 12,
                     "hp_current": 55, "hp_max": 55, "buffs": [],
                     "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
                    {"id": pip_tok, "char_id": pip["id"],
                     "name": pip["name"], "initiative": 8,
                     "hp_current": 40, "hp_max": 40, "buffs": [],
                     "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
                ],
                "turn_index": 0, "round": 1, "active": True,
            },
        )

        fear_cast = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": lyra["id"],
                "spell_index": 19,  # Fear
                "slot_level": 3,
                "class_slug": "bard",
                "target_character_id": pip["id"],
                "target_combatant_id": pip_tok,
                "target_name": pip["name"],
                "override": True,
                "override_range": True,
            },
        )
        assert fear_cast.status_code == 200, fear_cast.text
        prompt_id = fear_cast.json().get("auto_save_prompt_id")
        if not prompt_id:
            continue
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/roll_request/{prompt_id}/respond",
            json={"character_id": pip["id"]},
        )
        data = resp.json()
        if data.get("auto_buff_installed") == "Frightened":
            landed = True
            break

    assert landed, "no failed Wis save in 30 tries; couldn't install Frightened"

    # Verify the buff carries the v2.97.65 save_on_damage marker.
    pip_buffs = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/buffs"
    )).json().get("buffs", [])
    frightened = next(
        (b for b in pip_buffs if (b or {}).get("key") == "frightened"), None,
    )
    assert frightened is not None
    assert bool(frightened.get("save_on_damage")) is True
    assert int(frightened.get("repeated_save_dc") or 0) > 0

    gm_ws.mark()
    # Krieger attacks Pip. The attack will deal damage; the v2.97.65
    # hook should fire as part of the damage application.
    atk = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": krieger["id"],
            "attack_index": 0,  # Greataxe
            "target_combatant_id": pip_tok,
            "target_character_id": pip["id"],
            "target_name": pip["name"],
            "override": True,
            "override_range": True,
        },
    )
    assert atk.status_code == 200, atk.text

    # The attack may or may not hit on any given roll. If it hits and
    # deals damage, the v2.97.65 hook fires. If it misses (auto_apply
    # = no damage), the hook is a no-op. Loop a few attacks in this
    # case to land at least one damaging hit.
    fired = False
    for _ in range(20):
        await asyncio.sleep(0.15)
        msgs = gm_ws.buffered("roll")
        dt_msg = next(
            (m for m in msgs
             if "Damage-triggered save" in (m.get("data") or {}).get("note", "")
             and pip["name"] in (m.get("data") or {}).get("note", "")),
            None,
        )
        if dt_msg is not None:
            fired = True
            break
        # Re-attack to try landing a hit.
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": krieger["id"],
                "attack_index": 0,
                "target_combatant_id": pip_tok,
                "target_character_id": pip["id"],
                "target_name": pip["name"],
                "override": True,
                "override_range": True,
            },
        )

    assert fired, (
        f"expected a 🩸 'Damage-triggered save' broadcast for {pip['name']}; "
        f"notes={[(m.get('data') or {}).get('note') for m in gm_ws.buffered('roll')]}"
    )
