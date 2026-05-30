"""v2.97.71 — Confusion + Banishment catalog entries.

Confusion (Wis save, L4) installs the "confused" condition with RAW
end-of-turn save — automatically picks up the v2.97.62/69 PUT /battle
auto-fire via the v2.97.60 install stamps + v2.97.70 shared helper.
Banishment (Cha save, L4) installs the "banished" condition; RAW
does NOT grant an end-of-turn save, so the install is plain catalog
content.

Both tests bypass /cast_spell because no demo character has these
spells on their list; we directly seed the condition buff via PUT
/battle with the appropriate stamps to validate the catalog entry +
the auto-fire integration.
"""
import asyncio

from .conftest import CAMPAIGN_ID


def _confused_buff_with_stamps(caster_char_id: int, caster_name: str):
    """Return a Confused buff dict shaped like /respond's install
    output (with v2.97.60 + v2.97.70 stamps + v2.97.67 concentration
    fix)."""
    return {
        "key": "confused",
        "name": "Confused",
        "icon": "🌀",
        "duration_rounds": 10,
        "duration_max": 10,
        "concentration": False,  # v2.97.67 — target buffs are NOT concentration
        "source_char_id": caster_char_id,
        "source_char_name": caster_name,
        "source_spell": "Confusion",
        "effects": [
            "can't take reactions",
            "d10 at start of turn for random behavior",
            "save again at end of each turn (auto-fires)",
        ],
        # v2.97.60 — repeated-save plumbing
        "repeated_save_ability": "WIS",
        "repeated_save_dc": 14,  # spell DC for a Lv 7 caster typical
        "source_caster_creature_type": "",
        # Confusion has NO damage retrigger RAW
        "save_on_damage": False,
    }


def _banished_buff_without_repeated_save(caster_char_id: int, caster_name: str):
    """Return a Banished buff dict shaped like /respond's install
    output WITHOUT the v2.97.60 repeated-save stamps (Banishment RAW
    has no end-of-turn save)."""
    return {
        "key": "banished",
        "name": "Banished",
        "icon": "👻",
        "duration_rounds": 10,
        "duration_max": 10,
        "concentration": False,
        "source_char_id": caster_char_id,
        "source_char_name": caster_name,
        "source_spell": "Banishment",
        "effects": [
            "incapacitated on a harmless demiplane",
            "returns when spell ends or concentration breaks",
            "no end-of-turn save RAW",
        ],
        # NO repeated_save_ability / repeated_save_dc — Banishment
        # doesn't grant an end-of-turn save.
    }


async def test_confusion_installs_confused_with_repeated_save_stamps(
    gm_client, gm_ws, roster,
):
    """Seed Pip with a Confused buff carrying v2.97.60 stamps; advance
    the turn from Pip to another combatant; assert the 🔁 End-of-turn
    save broadcast fires for Pip's Confused buff via the v2.97.62
    auto-fire."""
    lyra = roster["Lyra Sunstrider"]
    pip = roster["Pip Quickfingers"]

    lyra_tok = f"tok_cfn_lyra_{lyra['id']}"
    pip_tok = f"tok_cfn_pip_{pip['id']}"

    # Clean any stale confused buff.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": pip["id"], "key": "confused"},
    )

    confused_buff = _confused_buff_with_stamps(lyra["id"], lyra["name"])

    # Seed battle: Lyra at turn 0, Pip with Confused at turn 1.
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [
                {"id": lyra_tok, "char_id": lyra["id"],
                 "name": lyra["name"], "initiative": 14,
                 "hp_current": 35, "hp_max": 35, "buffs": [],
                 "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
                {"id": pip_tok, "char_id": pip["id"],
                 "name": pip["name"], "initiative": 8,
                 "hp_current": 40, "hp_max": 40,
                 "buffs": [confused_buff],
                 "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
            ],
            "turn_index": 1, "round": 1, "active": True,
        },
    )

    gm_ws.mark()
    # End Pip's turn → advance to Lyra (turn 0, round 2).
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [
                {"id": lyra_tok, "char_id": lyra["id"],
                 "name": lyra["name"], "initiative": 14,
                 "hp_current": 35, "hp_max": 35, "buffs": [],
                 "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
                {"id": pip_tok, "char_id": pip["id"],
                 "name": pip["name"], "initiative": 8,
                 "hp_current": 40, "hp_max": 40,
                 "buffs": [confused_buff],
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
         and pip["name"] in (m.get("data") or {}).get("note", "")),
        None,
    )
    assert eot_msg is not None, (
        f"expected 🔁 'End-of-turn save' broadcast for {pip['name']}'s "
        f"Confused buff; got "
        f"notes={[(m.get('data') or {}).get('note') for m in roll_msgs]}"
    )


async def test_banishment_catalog_has_no_repeated_save_stamps(
    gm_client, gm_ws, roster,
):
    """Seed Pip with a Banished buff (NO repeated-save stamps);
    advance the turn; assert NO 🔁 End-of-turn save broadcast fires
    for the Banished buff — RAW Banishment doesn't grant such a save."""
    caelan = roster["Sir Caelan Lightbringer"]
    pip = roster["Pip Quickfingers"]

    caelan_tok = f"tok_bsh_caelan_{caelan['id']}"
    pip_tok = f"tok_bsh_pip_{pip['id']}"

    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": pip["id"], "key": "banished"},
    )

    banished_buff = _banished_buff_without_repeated_save(caelan["id"], caelan["name"])

    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [
                {"id": caelan_tok, "char_id": caelan["id"],
                 "name": caelan["name"], "initiative": 14,
                 "hp_current": 60, "hp_max": 60, "buffs": [],
                 "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
                {"id": pip_tok, "char_id": pip["id"],
                 "name": pip["name"], "initiative": 8,
                 "hp_current": 40, "hp_max": 40,
                 "buffs": [banished_buff],
                 "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
            ],
            "turn_index": 1, "round": 1, "active": True,
        },
    )

    gm_ws.mark()
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [
                {"id": caelan_tok, "char_id": caelan["id"],
                 "name": caelan["name"], "initiative": 14,
                 "hp_current": 60, "hp_max": 60, "buffs": [],
                 "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
                {"id": pip_tok, "char_id": pip["id"],
                 "name": pip["name"], "initiative": 8,
                 "hp_current": 40, "hp_max": 40,
                 "buffs": [banished_buff],
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
         and "Banished" in (m.get("data") or {}).get("note", "")),
        None,
    )
    assert eot_msg is None, (
        f"unexpected 🔁 'End-of-turn save' for Banished; RAW Banishment "
        f"doesn't grant such a save. notes="
        f"{[(m.get('data') or {}).get('note') for m in roll_msgs]}"
    )
