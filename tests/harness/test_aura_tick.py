"""v2.99.425 — Phase 5.1: aura tick substrate (_tick_auras).

docs/plans/auras.md P5.1 — on a turn advance, the server applies any
aura the new active combatant emits (a buff carrying
``effects.aura = {radius_ft, affects, <payload>}``) to the creatures in
its radius (owner-turn-start model). Off-grid (no token positions) every
in-init subject of the matching faction is affected — the Aura of
Protection fallback.

These tests install a synthetic aura buff via PUT /battle, then advance
the turn (PUT a new turn_index) so the emitter becomes active, and assert
the payload landed on the in-init subjects (NPC volatile temp_hp, read
from battle_update). The owner sits at init index 0; the turn advances
from index 1 → 0 so the emitter's turn starts.

Tests:
  - affects "all" → both NPC subjects gain the aura's temp HP; the
    emitter (self) does not.
  - affects "allies" with a PC emitter → NPC subjects are excluded (the
    faction filter), so no temp HP lands.
"""
import asyncio

from .conftest import CAMPAIGN_ID


def _npc(cid, name):
    return {
        "id": cid, "char_id": None, "name": name,
        "initiative": 5, "hp_current": 30, "hp_max": 30, "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _setup_and_tick(gm_client, gm_ws, roster, affects):
    """PUT a battle (emitter at index 0 with a temp_hp aura + two NPC
    subjects), start with someone else active (index 1), then advance to
    the emitter (index 0) to fire the tick. Returns the latest
    battle_update combatants keyed by id."""
    pip = roster["Pip Quickfingers"]
    owner_tok = f"tok_aura_owner_{pip['id']}"
    sub_a, sub_b = "tok_aura_a", "tok_aura_b"
    aura_buff = {
        "key": "test-aura", "name": "Test Aura",
        "duration_rounds": 10, "duration_max": 10, "concentration": False,
        "effects": {"aura": {
            "radius_ft": 0,          # 0 → no range gate (off-grid fallback)
            "affects": affects,
            "temp_hp": 7,
            "source": "test-aura", "label": "Test Aura",
        }},
    }
    combatants = [
        {"id": owner_tok, "char_id": pip["id"], "name": pip["name"],
         "initiative": 20, "hp_current": 40, "hp_max": 40,
         "buffs": [aura_buff],
         "economy": {"action": False, "bonus": False,
                     "reaction": False, "movement": 0}},
        _npc(sub_a, "Subject A"),
        _npc(sub_b, "Subject B"),
    ]
    # Start with a non-emitter active (index 1).
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 1, "round": 1,
              "active": True},
    )
    gm_ws.mark()
    # Advance to the emitter (index 0) → owner-turn-start tick fires.
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 2,
              "active": True},
    )
    await asyncio.sleep(0.3)
    bus = gm_ws.buffered("battle_update")
    assert bus, "no battle_update after turn advance"
    return {c.get("id"): c for c in (bus[-1]["data"].get("combatants") or [])}


async def test_aura_tick_affects_all(gm_client, gm_ws, roster):
    """affects=all → both NPC subjects gain 7 temp HP; emitter does not."""
    combs = await _setup_and_tick(gm_client, gm_ws, roster, "all")
    assert int(combs["tok_aura_a"].get("temp_hp") or 0) == 7
    assert int(combs["tok_aura_b"].get("temp_hp") or 0) == 7
    # The emitter (PC, self) is excluded from a non-"self" aura.
    owner = next(c for cid, c in combs.items() if cid.startswith("tok_aura_owner_"))
    assert int(owner.get("temp_hp") or 0) == 0


async def test_aura_tick_allies_excludes_enemies(gm_client, gm_ws, roster):
    """affects=allies with a PC emitter → NPC subjects (the opposite
    faction) get nothing."""
    combs = await _setup_and_tick(gm_client, gm_ws, roster, "allies")
    assert int(combs["tok_aura_a"].get("temp_hp") or 0) == 0
    assert int(combs["tok_aura_b"].get("temp_hp") or 0) == 0
