"""v2.93.0 — extends the v2.92.0 spell-slot refund to the
Counterspell reaction-cast path.

v2.70.0 wired Counterspell as a reaction option on the
``spell_cast_near`` prompt (Lyra casts Suggestion → Thalindra gets
prompted → Thalindra POSTs /use_reaction with reaction_key=
``cast-counterspell``). The slot was decremented but the cast had no
``cast_id``, so the v2.92.0 ↶ Undo machinery couldn't refund it. This
commit generates a cast_id at the slot-decrement site, logs a
``spell_slot_spend`` entry, and surfaces the cast_id on the
``feature_used`` broadcast so the roll-log card can wire its Undo
button.

Tests:
  - happy path: drive the same Lyra→Thalindra Counterspell flow used
    by test_reaction_prompt::test_cast_counterspell_consumes_slot,
    capture the ``cast_id`` from the feature_used broadcast, POST
    /undo_attack_damage with it, assert the spell_slot_update
    broadcast carries the L3 slot's ``used`` decremented by 1 from
    the post-cast count.

Filed for follow-up (CHANGELOG note): Shield, Absorb Elements,
Hellish Rebuke, Silvery Barbs reaction-cast branches in
/use_reaction follow the same shape (slot decrement + feature_used)
and need the same plumbing. Each one is a small near-identical
patch; doing them in one bulk commit risked masking the
Counterspell smoke test if any single branch had a copy-paste typo,
so they're queued individually.
"""
import asyncio

from .conftest import CAMPAIGN_ID


async def _long_rest(gm_client, char_id: int) -> None:
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )
    assert resp.status_code == 200, resp.text


async def _place_token(gm_client, char_id: int, x: float, y: float) -> None:
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/place-token",
        json={"x": float(x), "y": float(y)},
    )
    assert resp.status_code == 200, resp.text


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": combatants,
            "turn_index": 0,
            "round": 1,
            "active": True,
        },
    )


def _make_combatant(name: str, char_id: int, init: int, hp: int):
    return {
        "id": f"tok_csu_{char_id}",
        "char_id": char_id,
        "name": name,
        "initiative": init,
        "hp_current": hp,
        "hp_max": max(hp, 1),
        "buffs": [],
        "economy": {
            "action": False, "bonus": False,
            "reaction": False, "movement": 0,
        },
    }


async def test_undo_refunds_counterspell_slot(gm_client, gm_ws, roster):
    lyra = roster["Lyra Sunstrider"]
    thalindra = roster["Thalindra Moonwhisper"]
    krieger = roster["Krieger Stonefist"]
    await _long_rest(gm_client, lyra["id"])
    await _long_rest(gm_client, thalindra["id"])
    await _place_token(gm_client, lyra["id"], 300.0, 300.0)
    await _place_token(gm_client, thalindra["id"], 370.0, 300.0)
    await _place_token(gm_client, krieger["id"], 440.0, 300.0)

    thal_cid = f"tok_csu_{thalindra['id']}"
    krieg_cid = f"tok_csu_kr_{krieger['id']}"
    await _seed_battle(gm_client, [
        _make_combatant(lyra["name"], lyra["id"], init=14, hp=40),
        {
            "id": thal_cid,
            "char_id": thalindra["id"],
            "name": thalindra["name"],
            "initiative": 10,
            "hp_current": 32, "hp_max": 32,
            "buffs": [],
            "economy": {
                "action": False, "bonus": False,
                "reaction": False, "movement": 0,
            },
        },
        {
            "id": krieg_cid,
            "char_id": krieger["id"],
            "name": krieger["name"],
            "initiative": 8,
            "hp_current": 75, "hp_max": 75,
            "buffs": [],
            "economy": {
                "action": False, "bonus": False,
                "reaction": False, "movement": 0,
            },
        },
    ])
    await asyncio.sleep(0.15)
    gm_ws.mark()

    # Trigger the Counterspell prompt: Lyra casts Suggestion targeting
    # Krieger, with Thalindra within 60 ft (per the spell_cast_near
    # walker's range gate).
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": lyra["id"],
            "spell_index": 9,  # Suggestion in Lyra's bard slot list
            "slot_level": 2,
            "class_slug": "bard",
            "target_combatant_id": krieg_cid,
            "target_character_id": krieger["id"],
            "target_name": krieger["name"],
            "override": True,
            "override_range": True,
        },
    )
    assert resp.status_code == 200, resp.text

    await asyncio.sleep(0.2)
    prompts = [
        m for m in gm_ws.buffered("reaction_prompt")
        if (m.get("data") or {}).get("watcher_char_id") == thalindra["id"]
        and (m.get("data") or {}).get("trigger_event") == "spell_cast_near"
    ]
    assert prompts, "expected spell_cast_near prompt for Thalindra"
    prompt_id = prompts[0]["data"]["prompt_id"]

    gm_ws.mark()
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_reaction",
        json={
            "prompt_id": prompt_id,
            "reaction_key": "cast-counterspell",
            "watcher_char_id": thalindra["id"],
        },
    )
    assert cast.status_code == 200, cast.text

    await asyncio.sleep(0.2)
    # Capture the cast_id off the feature_used broadcast.
    fu = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "counterspell-cast"
        and (m.get("data") or {}).get("character_id") == thalindra["id"]
    ]
    assert fu, "expected feature_used(source=counterspell-cast) broadcast"
    cast_id = fu[-1]["data"].get("cast_id")
    assert cast_id, (
        f"feature_used broadcast for Counterspell is missing cast_id; "
        f"payload: {fu[-1]['data']}"
    )

    # Capture the post-cast L3 slot used count off the cast-time
    # spell_slot_update broadcast so we can compare to the post-undo
    # value below.
    slot_msgs = [
        m for m in gm_ws.buffered("spell_slot_update")
        if (m.get("data") or {}).get("character_id") == thalindra["id"]
        and int((m.get("data") or {}).get("level") or 0) == 3
    ]
    assert slot_msgs, "expected spell_slot_update L3 for Thalindra"
    post_cast_used = int(slot_msgs[-1]["data"]["used"])
    post_cast_total = int(slot_msgs[-1]["data"]["total"])

    # Re-mark so wait_for picks up the refund's broadcast, not the
    # cast's earlier one (same shape, same wait_for selector).
    gm_ws.mark()
    undo = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/undo_attack_damage",
        json={"attack_id": cast_id},
    )
    assert undo.status_code == 200, undo.text
    assert undo.json()["ok"] is True

    msg = await gm_ws.wait_for("spell_slot_update")
    data = msg["data"]
    assert data["character_id"] == thalindra["id"]
    assert data["level"] == 3
    assert data["total"] == post_cast_total
    assert data["used"] == post_cast_used - 1, (
        f"Counterspell slot wasn't refunded: post-cast used="
        f"{post_cast_used}, post-undo used={data['used']}"
    )
