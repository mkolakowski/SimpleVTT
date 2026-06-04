"""v2.99.194 — Halfling Lucky audit regression: NPC attacks targeting
a Halfling PC don't trigger Halfling Lucky.

Phase A.1 audit follow-up from `docs/plans/class-content-status.md`
(updated v2.99.193). v2.99.21 wired Halfling Lucky into `/attack`
(PC attacker rolls a natural 1 → reroll). v2.99.22 wired it into
ability/skill/initiative checks via `/roll`. v2.99.13 wired it into
saves via `/roll_request/respond`.

**RAW (PHB p.28):** "When you roll a 1 on the d20 for an attack
roll, ability check, or saving throw, you can reroll the die and
must use the new roll." The Halfling Lucky reroll fires on the
**roller's** d20 only — not on incoming attacks where someone else
rolled the d20.

This test pins the audit conclusion in regression: when a Halfling
PC (Pip Quickfingers) is the TARGET of an NPC attack via
`/npc_attack`, no `feature_used(source=halfling-lucky)` broadcast
fires for Pip — even when the NPC's attack d20 lands on 1 (which
would be Pip's lucky number IF Pip had rolled it). The NPC rolled,
not Pip; Lucky doesn't trigger.

This is documenting behavior, not changing it. The current
`_pc_has_halfling_lucky` hooks are at the right places.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _seed_dice(gm_client, seed: int):
    """Force the next d20 result via the TEST_MODE dice seed endpoint."""
    resp = await gm_client.post(
        "/api/test/dice/seed", json={"seed": seed},
    )
    assert resp.status_code == 200, resp.text


async def _seed_battle(gm_client, combatants):
    return await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


async def test_npc_attack_on_halfling_pc_no_lucky_reroll(
    gm_client, gm_ws, roster,
):
    """An NPC attacks Pip (Halfling Rogue) via /npc_attack. Even
    after many rolls (some of which will land natural 1s), no
    `feature_used(source=halfling-lucky)` broadcast fires for Pip.
    The Halfling is the TARGET, not the ROLLER.
    """
    pip = roster["Pip Quickfingers"]
    pip_tok = f"tok_hlna_pip_{pip['id']}"
    npc_tok = "tok_hlna_bandit"
    await _seed_battle(gm_client, [
        {"id": pip_tok, "char_id": pip["id"],
         "name": pip["name"], "initiative": 8,
         "hp_current": 47, "hp_max": 47,
         "buffs": [],
         "economy": {"action": False, "bonus": False,
                     "reaction": False, "movement": 0}},
        {"id": npc_tok, "name": "Bandit",
         "initiative": 12, "hp_current": 11, "hp_max": 11,
         "buffs": [],
         "economy": {"action": False, "bonus": False,
                     "reaction": False, "movement": 0}},
    ])
    gm_ws.mark()
    # Fire 30 NPC attacks at Pip; given d20 distribution, at least
    # one or two should land natural 1 — enough to surface a
    # regression if the Lucky hook were wrongly applied to NPC
    # attacks on the Halfling.
    for i in range(30):
        await _seed_dice(gm_client, 1000 + i)
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/npc_attack",
            json={
                "combatant_id": npc_tok,
                "action_id": "bandit-scimitar",
                "action_name": "Scimitar",
                "attack_bonus": "+3",
                "damage": "1d6+1",
                "damage_type": "slashing",
                "range": "5 ft",
                "target_combatant_id": pip_tok,
            },
        )
        assert r.status_code == 200, r.text
    # Pip is the demo Halfling. If any halfling-lucky broadcast
    # fired for Pip, the regression is real.
    feats = gm_ws.buffered("feature_used")
    lucky_for_pip = [
        m for m in feats
        if (m.get("data") or {}).get("source") == "halfling-lucky"
        and (m.get("data") or {}).get("character_id") == pip["id"]
    ]
    assert not lucky_for_pip, (
        f"v2.99.194 audit regression: Halfling Lucky should NOT fire "
        f"when Pip is the TARGET of an NPC attack (the NPC rolled, "
        f"not Pip). Got {len(lucky_for_pip)} spurious "
        f"feature_used(source=halfling-lucky) broadcast(s)."
    )
