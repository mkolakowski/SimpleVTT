"""v2.99.186 — NPC mirror: Subtle Spell suppresses Counterspell prompts.

Closes a v2.99.173 filed item. v2.99.173 wired the PC side:
`_emit_counterspell_prompts(was_subtle=True)` short-circuits, and
`/cast_spell` derives `was_subtle` from `_caster_has_subtle_pending`.
The NPC mirror at `/npc_cast_spell` didn't have parallel plumbing —
an NPC carrying `metamagic-subtle-pending` (e.g. seeded via /battle
PUT by the GM in a "this hag knows Subtle" encounter) would still
emit the Counterspell prompt.

v2.99.186 closes that gap:
  - `_npc_has_subtle_pending(campaign_id, combatant_id)` —
    combatant-id-keyed mirror of `_caster_has_subtle_pending`.
  - `_consume_npc_subtle_pending(campaign_id, combatant_id)` —
    one-shot remover (PC path uses `_remove_buff` on char_id;
    NPCs need a combatant-id remover).
  - `/npc_cast_spell` derives `_npc_was_subtle`, broadcasts the
    🤫 marker, stamps `was_subtle` on the cast payload, and
    passes the flag to `_emit_counterspell_prompts`.

Tests:
  - Seed an NPC + a PC watcher with Counterspell in a battle, seed
    the NPC's combatant with a `metamagic-subtle-pending` buff via
    /battle PUT, then call /npc_cast_spell. Verify the cast payload
    carries `was_subtle: True` and no Counterspell prompt fires.
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


async def test_npc_cast_subtle_suppresses_counterspell_prompt(
    gm_client, gm_ws, roster,
):
    """NPC casts with metamagic-subtle-pending on its combatant.
    No reaction_prompt(spell_cast_near) carrying a cast-counterspell
    option should fire — the v2.99.186 gate at /npc_cast_spell
    consumes the buff + flags `was_subtle` for the walker.
    """
    thalindra = roster["Thalindra Moonwhisper"]
    await _place_token(gm_client, thalindra["id"], 420.0, 350.0)
    npc_tok = "tok_npc_subtle_synthetic"
    # Seed NPC + PC watcher in battle. NPC carries Subtle pending.
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": npc_tok, "name": "Quiet Hag",
             "initiative": 12, "hp_current": 40, "hp_max": 40,
             "buffs": [{
                 "key": "metamagic-subtle-pending",
                 "name": "Subtle Spell armed",
                 "icon": "🤫",
                 "duration_rounds": 1,
                 "duration_max": 1,
                 "concentration": False,
                 "source": "metamagic-subtle-spell",
                 "effects": {"counterspell_immune": True},
             }],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": f"tok_npcs_th_{thalindra['id']}",
             "char_id": thalindra["id"], "name": thalindra["name"],
             "initiative": 8, "hp_current": 30, "hp_max": 30,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    # PATCH Counterspell onto Thalindra's spell list so she'd
    # qualify for the prompt absent the Subtle gate.
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-fields",
        json={"spells": [
            {"name": "Counterspell", "level": 3, "_slug": "counterspell",
             "prepared": True, "casting_time": "1 reaction"},
        ]},
    )
    gm_ws.mark()
    # NPC casts a leveled spell.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/npc_cast_spell",
        json={
            "combatant_id": npc_tok,
            "spell_name": "Phantasmal Force",
            "spell_level": 2,
            "spell_range": "60 feet",
            "save_ability": "INT",
            "save_dc": 14,
            "target_combatant_id": f"tok_npcs_th_{thalindra['id']}",
        },
    )
    assert r.status_code == 200, r.text
    await asyncio.sleep(0.3)
    # Verify spell_cast carries was_subtle: True.
    casts = gm_ws.buffered("spell_cast")
    assert casts, "expected at least one spell_cast broadcast"
    last_cast = casts[-1]
    assert (last_cast.get("data") or {}).get("was_subtle") is True, (
        f"v2.99.186: NPC cast should stamp was_subtle=True; "
        f"got {last_cast.get('data')}"
    )
    # Verify 🤫 marker fired.
    feats = gm_ws.buffered("feature_used")
    subtle_marks = [
        m for m in feats
        if (m.get("data") or {}).get("source")
        == "metamagic-subtle-spell-consumed"
    ]
    assert subtle_marks, (
        "v2.99.186: expected a metamagic-subtle-spell-consumed "
        "feature_used broadcast after NPC subtle cast"
    )
    # Verify NO reaction_prompt(spell_cast_near) was emitted.
    msgs = gm_ws.buffered("reaction_prompt")
    spell_cast_prompts = [
        m for m in msgs
        if (m.get("data") or {}).get("trigger_event") == "spell_cast_near"
    ]
    assert not spell_cast_prompts, (
        f"v2.99.186: NPC Subtle Spell should suppress the "
        f"Counterspell prompt; got {len(spell_cast_prompts)} "
        f"prompt(s)"
    )
