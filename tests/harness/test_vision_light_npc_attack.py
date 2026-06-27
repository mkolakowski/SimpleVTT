"""v2.707.0 — Vision & Light Phase 2, NPC mirror (docs/plans/vision-and-light.md).

Wires `_visibility_between` into the NPC `/npc_attack` pipeline (symmetric
with the PC `/attack` wiring shipped in v2.706.0), via
`_npc_attack_vision_edges` → the shared `_compute_vision_edges` core:
  - a target the NPC can't see (lighting model) → DISADVANTAGE
    (`roll_state_applied` "disadvantage_cant_see");
  - an NPC the *target* can't see → ADVANTAGE ("advantage_unseen_attacker");
  - a bright map short-circuits (hot path untouched).

The NPC attacker carries a real token (positions come from the map). Senses
ride combatant buffs — the NPC's own (read directly) and the PC target's
(read by char_id).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

NPC_TOK = "npc_vis_atk"
GAR_TOK = "tok_vis_npc_gar"
_DV = [{"key": "dv", "name": "Darkvision", "effects": {"darkvision_ft": 60}}]


def _gar_cb(garrik, buffs=None):
    return {"id": GAR_TOK, "char_id": garrik["id"], "name": garrik["name"],
            "initiative": 8, "hp_current": 60, "hp_max": 60,
            "buffs": buffs or [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


def _npc_cb(source_token_id, buffs=None):
    return {"id": NPC_TOK, "char_id": None, "name": "Gloom Stalker",
            "token_template_id": 1, "source_token_id": source_token_id,
            "initiative": 20, "hp_current": 30, "hp_max": 30,
            "buffs": buffs or [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


async def _set_ambient(gm_client, map_id, level):
    r = await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings/maps/{map_id}/ambient_light",
        json={"ambient_light": level})
    assert r.status_code == 200, r.text


async def _seed(gm_client, npc_token_id, garrik, npc_buffs=None, gar_buffs=None):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [_npc_cb(npc_token_id, npc_buffs),
                             _gar_cb(garrik, gar_buffs)],
              "turn_index": 0, "round": 1, "active": True})


async def _npc_attack(gm_client):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/npc_attack",
        json={"combatant_id": NPC_TOK, "action_name": "Longbow",
              "attack_bonus": "+5", "damage": "1d8+3",
              "damage_type": "piercing", "target_combatant_id": GAR_TOK})
    assert r.status_code == 200, r.text
    return r.json().get("roll_state_applied") or ""


@pytest_asyncio.fixture
async def npc_scene(gm_client, roster):
    """An NPC token + Garrik (target) 5 ft apart on the active map. Restores
    bright + clears the battle on teardown."""
    garrik = roster["Garrik Ironside"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/place-token",
        json={"x": 420.0, "y": 350.0})
    npc_tok = (await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/tokens",
        json={"label": "Gloom Stalker", "x": 350.0, "y": 350.0})).json()
    map_id = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/tokens")).json()["map_id"]
    try:
        yield {"garrik": garrik, "npc_token_id": npc_tok["id"], "map_id": map_id}
    finally:
        await _set_ambient(gm_client, map_id, "bright")
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={"combatants": [], "turn_index": 0, "round": 1,
                  "active": False})


async def test_npc_cant_see_target_disadvantage(gm_client, npc_scene):
    """Dark map: the NPC (no senses) can't see Garrik (darkvision, so Garrik
    sees the NPC) → pure disadvantage."""
    sc = npc_scene
    await _seed(gm_client, sc["npc_token_id"], sc["garrik"],
               npc_buffs=[], gar_buffs=list(_DV))
    await _set_ambient(gm_client, sc["map_id"], "dark")
    state = await _npc_attack(gm_client)
    assert state == "disadvantage_cant_see", state


async def test_npc_unseen_attacker_advantage(gm_client, npc_scene):
    """Dark map: the NPC (darkvision) sees Garrik, but Garrik (no senses)
    can't see the NPC → the NPC is unseen → advantage."""
    sc = npc_scene
    await _seed(gm_client, sc["npc_token_id"], sc["garrik"],
               npc_buffs=list(_DV), gar_buffs=[])
    await _set_ambient(gm_client, sc["map_id"], "dark")
    state = await _npc_attack(gm_client)
    assert state == "advantage_unseen_attacker", state


async def test_npc_bright_map_no_edge(gm_client, npc_scene):
    """Default bright map → the helper short-circuits → no lighting edge."""
    sc = npc_scene
    await _seed(gm_client, sc["npc_token_id"], sc["garrik"],
               npc_buffs=[], gar_buffs=[])
    state = await _npc_attack(gm_client)
    assert "cant_see" not in state and "unseen_attacker" not in state, state
