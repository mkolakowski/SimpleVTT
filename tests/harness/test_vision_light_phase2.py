"""v2.706.0 — Vision & Light Phase 2 (docs/plans/vision-and-light.md).

Wires `_visibility_between` into the PC `/attack` pipeline (both the bonused
and bonusless branches via the shared `_attack_vision_edges` helper):
  - a target the attacker can't see (lighting model) → attack DISADVANTAGE
    (`roll_state_applied` == "disadvantage_cant_see"), no manual flag needed;
  - an attacker the *target* can't see → ADVANTAGE
    ("advantage_unseen_attacker");
  - mutual blindness → adv + dis cancel ("canceled_...").
The manual `attacker_cant_see_target` body flag stays a GM override, and a
bright map keeps the hot path untouched (the helper short-circuits).

Senses ride combatant buffs (read by the resolver). Attacker = Pip, target =
Garrik, 5 ft apart on the active map.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

PIP_TOK = "tok_v2_pip"
GAR_TOK = "tok_v2_gar"


def _cb(tok_id, char, init, buffs=None):
    return {"id": tok_id, "char_id": char["id"], "name": char["name"],
            "initiative": init, "hp_current": 60, "hp_max": 60,
            "buffs": buffs or [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


async def _set_ambient(gm_client, map_id, level):
    r = await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings/maps/{map_id}/ambient_light",
        json={"ambient_light": level})
    assert r.status_code == 200, r.text


async def _seed(gm_client, pip, garrik, pip_buffs=None, gar_buffs=None):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [_cb(PIP_TOK, pip, 20, pip_buffs),
                             _cb(GAR_TOK, garrik, 8, gar_buffs)],
              "turn_index": 0, "round": 1, "active": True})


async def _attack(gm_client, pip, extra=None):
    body = {"character_id": pip["id"], "attack_index": 0,
            "target_combatant_id": GAR_TOK, "override": True}
    if extra:
        body.update(extra)
    a = await gm_client.post(f"/api/campaign/{CAMPAIGN_ID}/attack", json=body)
    assert a.status_code == 200, a.text
    return a.json().get("roll_state_applied") or ""


_DV = [{"key": "dv", "name": "Darkvision", "effects": {"darkvision_ft": 60}}]


@pytest_asyncio.fixture
async def scene(gm_client, roster):
    """Pip + Garrik placed 5 ft apart on the active map. Restores bright +
    clears the battle on teardown."""
    pip, garrik = roster["Pip Quickfingers"], roster["Garrik Ironside"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/rest",
        json={"type": "long"})
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/place-token",
        json={"x": 350.0, "y": 350.0})
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/place-token",
        json={"x": 420.0, "y": 350.0})
    map_id = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/tokens")).json()["map_id"]
    try:
        yield {"pip": pip, "garrik": garrik, "map_id": map_id}
    finally:
        await _set_ambient(gm_client, map_id, "bright")
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={"combatants": [], "turn_index": 0, "round": 1,
                  "active": False})


async def test_dark_target_unseen_disadvantage(gm_client, scene):
    """Dark map: Pip (no senses) can't see Garrik (darkvision, so Garrik DOES
    see Pip) → pure disadvantage, no manual flag passed."""
    sc = scene
    await _seed(gm_client, sc["pip"], sc["garrik"], pip_buffs=[],
               gar_buffs=list(_DV))
    await _set_ambient(gm_client, sc["map_id"], "dark")
    state = await _attack(gm_client, sc["pip"])
    assert state == "disadvantage_cant_see", state


async def test_dark_unseen_attacker_advantage(gm_client, scene):
    """Dark map: Pip (darkvision) sees Garrik, but Garrik (no senses) can't
    see Pip → attacker is unseen → advantage."""
    sc = scene
    await _seed(gm_client, sc["pip"], sc["garrik"], pip_buffs=list(_DV),
               gar_buffs=[])
    await _set_ambient(gm_client, sc["map_id"], "dark")
    state = await _attack(gm_client, sc["pip"])
    assert state == "advantage_unseen_attacker", state


async def test_dark_mutual_blind_cancels(gm_client, scene):
    """Dark map, neither has senses → each is unseen to the other → adv + dis
    cancel to a straight roll."""
    sc = scene
    await _seed(gm_client, sc["pip"], sc["garrik"], pip_buffs=[], gar_buffs=[])
    await _set_ambient(gm_client, sc["map_id"], "dark")
    state = await _attack(gm_client, sc["pip"])
    assert state.startswith("canceled_"), state
    assert "unseen_attacker" in state and "cant_see" in state, state


async def test_dark_both_darkvision_no_edge(gm_client, scene):
    """Dark map, both have darkvision (≥ range) → both merely obscured (dim) →
    no attack edge from the lighting model."""
    sc = scene
    await _seed(gm_client, sc["pip"], sc["garrik"], pip_buffs=list(_DV),
               gar_buffs=list(_DV))
    await _set_ambient(gm_client, sc["map_id"], "dark")
    state = await _attack(gm_client, sc["pip"])
    assert "cant_see" not in state and "unseen_attacker" not in state, state


async def test_bright_map_no_edge(gm_client, scene):
    """Default bright map → the helper short-circuits → no lighting edge."""
    sc = scene
    await _seed(gm_client, sc["pip"], sc["garrik"], pip_buffs=[], gar_buffs=[])
    # ambient stays bright (default)
    state = await _attack(gm_client, sc["pip"])
    assert "cant_see" not in state and "unseen_attacker" not in state, state


async def test_manual_override_still_forces_disadvantage(gm_client, scene):
    """Bright map (helper short-circuits) but the GM passes the manual
    attacker_cant_see_target flag → disadvantage still applies."""
    sc = scene
    await _seed(gm_client, sc["pip"], sc["garrik"], pip_buffs=[], gar_buffs=[])
    state = await _attack(gm_client, sc["pip"],
                          extra={"attacker_cant_see_target": True})
    assert state == "disadvantage_cant_see", state
