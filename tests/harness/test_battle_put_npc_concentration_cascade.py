"""v2.99.185 — /battle PUT auto-triggers NPC concentration cleanup.

Closes a v2.99.179 filed item. v2.99.179 wired the
`_drop_paired_concentration_buffs_npc` cascade + a polymorph-
active revert hook, but the only way to fire the cascade was
manually (or via NPC concentration save failure). The /battle
PUT path — the canonical "edit NPC's buff list" entry — didn't
trigger the cascade.

v2.99.185 adds the detection: compare prev vs new combatants for
each NPC (no char_id). If an NPC's concentration buff was
present pre-PUT but absent post-PUT, fire the cascade for that
NPC's combatant_id.

This closes the full Polymorph mechanical chain for NPC casters:
  - NPC has concentration anchor + polymorph-active marker on
    PC target (v2.99.179)
  - GM removes the NPC's concentration buff via /battle PUT
  - v2.99.185 detects + fires the cascade
  - The polymorph-active marker on the target is dropped
  - v2.99.172's revert hook fires + restores the target's sheet
    + token disguise

Tests:
  - Setup an NPC with a concentration buff + a PC target with a
    polymorph-active marker sourced from the NPC.
  - /battle PUT with the NPC's concentration buff removed.
  - Verify the PC target's polymorph-active marker is gone.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _place_token(gm_client, char_id, x, y):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/place-token",
        json={"x": float(x), "y": float(y)},
    )
    assert r.status_code == 200, r.text
    return r.json()


async def _get_buffs(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    return r.json().get("buffs") or []


async def test_battle_put_drops_npc_concentration_buffs(
    gm_client, roster,
):
    """NPC has concentration buff + PC target has marker. /battle
    PUT with the NPC's concentration removed → marker dropped via
    cascade.
    """
    krieger = roster["Krieger Stonefist"]
    await _place_token(gm_client, krieger["id"], 350.0, 350.0)
    npc_tok = "tok_bput_npc_synthetic"
    kr_tok = f"tok_bput_kri_{krieger['id']}"
    # Seed NPC + PC with target-side marker buff sourced from NPC.
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": npc_tok, "name": "Hag",
             "initiative": 10, "hp_current": 60, "hp_max": 60,
             "buffs": [{
                 "key": "concentration-polymorph",
                 "name": "Concentrating: Polymorph",
                 "icon": "🦌",
                 "duration_rounds": 600,
                 "duration_max": 600,
                 "concentration": True,
                 "source": "polymorph-anchor",
                 "source_combatant_id": npc_tok,
             }],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": kr_tok, "char_id": krieger["id"],
             "name": krieger["name"], "initiative": 8,
             "hp_current": 75, "hp_max": 75,
             "buffs": [{
                 "key": "polymorph-active",
                 "name": "Polymorphed (Wolf)",
                 "icon": "🦌",
                 "duration_rounds": 600,
                 "duration_max": 600,
                 "concentration": True,
                 "source": "polymorph-spell",
                 "source_combatant_id": npc_tok,
                 "effects": {
                     "polymorph_active": True,
                     "form_name": "Wolf",
                     "form_slug": "wolf",
                 },
             }],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    # Sanity: Krieger has the polymorph-active marker.
    pre_buffs = await _get_buffs(gm_client, krieger["id"])
    pre_keys = {(b or {}).get("key") for b in pre_buffs}
    assert "polymorph-active" in pre_keys
    # /battle PUT with the NPC's concentration buff removed.
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": npc_tok, "name": "Hag",
             "initiative": 10, "hp_current": 60, "hp_max": 60,
             "buffs": [],  # concentration dropped
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": kr_tok, "char_id": krieger["id"],
             "name": krieger["name"], "initiative": 8,
             "hp_current": 75, "hp_max": 75,
             "buffs": pre_buffs,  # PC's buffs unchanged here
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    # The cascade should have removed Krieger's polymorph-active
    # marker (and triggered the v2.99.172 revert hook, which the
    # v2.99.179 NPC mirror cascade fires too).
    post_buffs = await _get_buffs(gm_client, krieger["id"])
    post_keys = {(b or {}).get("key") for b in post_buffs}
    assert "polymorph-active" not in post_keys, (
        f"Cascade should drop polymorph-active when NPC's "
        f"concentration is removed via /battle PUT; got "
        f"buffs={post_keys}"
    )
