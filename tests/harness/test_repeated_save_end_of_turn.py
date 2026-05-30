"""v2.97.62 — auto-fire repeated saves at end of turn.

When PUT /battle advances ``turn_index`` from N → N+1, the v2.97.62
hook walks the combatant at index N (the one whose turn just ended)
and auto-rolls every repeatable save buff they carry. RAW Hold
Person / Fear / etc.: "at the end of each of its turns, the target
can make another <ability> saving throw."

Test flow:
- Seed battle with Lyra (creature_type="fiend" override) at turn 0
  and Pip at turn 1.
- Lyra casts Fear on Pip from her slot, loops until Pip fails the
  install save and Frightened lands with v2.97.60 install-time stamps.
- The battle's turn_index is currently 0 (Lyra's turn). Advance to
  turn_index=1 via PUT /battle so the prior-active is Lyra.
- That doesn't test what we want — we want Pip's end-of-turn save.
  So: advance to turn_index=0 (back to Lyra after Pip's turn), which
  means Pip's turn ended.

Actually for clarity: we want a turn shift FROM Pip TO someone else.
So:
  1. Set turn_index=1 (Pip's turn).
  2. PUT /battle with turn_index=0 (Lyra back in turn). This is
     "Pip's turn ended → Lyra's turn starts."
  3. The v2.97.62 hook sees prev_turn=1 != new_turn=0 and walks the
     combatant at prev_turn_index=1 (Pip).
  4. Assert: gm_ws captures a 'roll' broadcast whose ``note`` contains
     "End-of-turn save" and the saver is Pip.
"""
import asyncio

from .conftest import CAMPAIGN_ID


async def _long_rest(gm_client, char_id: int) -> None:
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )
    assert resp.status_code == 200, resp.text


async def test_end_of_turn_auto_fires_repeated_save(
    gm_client, gm_ws, roster,
):
    """Lyra (fiend) frightens Pip; PUT /battle advances turn from
    Pip→Lyra; the v2.97.62 hook auto-rolls Pip's WIS save against
    Frightened and broadcasts an 'End-of-turn save' roll entry."""
    lyra = roster["Lyra Sunstrider"]
    pip = roster["Pip Quickfingers"]

    lyra_tok = f"tok_rs_eot_lyra_{lyra['id']}"
    pip_tok = f"tok_rs_eot_pip_{pip['id']}"

    # Install Frightened (loop). Then capture the buff list snapshot
    # so we can include it in the subsequent PUT /battle calls.
    landed = False
    for _ in range(30):
        await _long_rest(gm_client, lyra["id"])
        await _long_rest(gm_client, pip["id"])
        for _stale in (
            "frightened", "paralyzed", "charmed", "baned", "faerie-fired",
            "protection-from-evil-and-good", "heroism", "bless",
        ):
            await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/end_buff",
                json={"character_id": pip["id"], "key": _stale},
            )
        # Seed: Lyra at turn 0, Pip at turn 1.
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={
                "combatants": [
                    {"id": lyra_tok, "char_id": lyra["id"],
                     "name": lyra["name"], "initiative": 12,
                     "hp_current": 35, "hp_max": 35, "buffs": [],
                     "creature_type": "fiend",
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
                "spell_index": 19,
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

    # Confirm Pip carries Frightened with the v2.97.60 stamps.
    pip_buffs = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/buffs"
    )).json().get("buffs", [])
    frightened = next(
        (b for b in pip_buffs if (b or {}).get("key") == "frightened"), None,
    )
    assert frightened is not None
    assert int(frightened.get("repeated_save_dc") or 0) > 0

    # The test seed put turn_index=0 (Lyra's slot). Move to turn 1
    # (Pip's slot), then back to turn 0 — that's "Pip's turn ended".
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [
                {"id": lyra_tok, "char_id": lyra["id"],
                 "name": lyra["name"], "initiative": 12,
                 "hp_current": 35, "hp_max": 35, "buffs": [],
                 "creature_type": "fiend",
                 "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
                {"id": pip_tok, "char_id": pip["id"],
                 "name": pip["name"], "initiative": 8,
                 "hp_current": 40, "hp_max": 40,
                 "buffs": pip_buffs,
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
                 "name": lyra["name"], "initiative": 12,
                 "hp_current": 35, "hp_max": 35, "buffs": [],
                 "creature_type": "fiend",
                 "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
                {"id": pip_tok, "char_id": pip["id"],
                 "name": pip["name"], "initiative": 8,
                 "hp_current": 40, "hp_max": 40,
                 "buffs": pip_buffs,
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
         and pip["name"] in (m.get("data") or {}).get("note", "")),
        None,
    )
    assert eot_msg is not None, (
        f"expected a 🔁 End-of-turn save broadcast for {pip['name']}; "
        f"notes={[(m.get('data') or {}).get('note') for m in roll_msgs]}"
    )
