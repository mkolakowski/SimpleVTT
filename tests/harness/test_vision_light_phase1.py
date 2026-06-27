"""v2.705.0 — Vision & Light Phase 1 (docs/plans/vision-and-light.md).

The `_visibility_between` resolver, exposed read-only at
`GET /api/campaign/{cid}/visibility?attacker_combatant_id=&target_combatant_id=`
→ `{visibility, illumination, range_ft, senses}` (visibility ∈ seen /
obscured / unseen). No `/attack` wiring yet (Phase 2).

Matrix (attacker Pip, target Garrik, 1 cell / 5 ft apart on the active map):
  - bright ambient → seen.
  - dark + no senses → unseen.
  - dark + darkvision (≥ range) → obscured (lightly obscured, no attack edge).
  - dark + truesight → seen (sense grants sight regardless of light).
  - dark + the target carrying its own light → seen (illumination bright).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

PIP_TOK = "tok_vis_pip"
GAR_TOK = "tok_vis_gar"


async def _patch_sheet(gm_client, char_id, fields):
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json=fields,
    )
    assert r.status_code == 200, r.text


async def _set_ambient(gm_client, map_id, level):
    r = await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings/maps/{map_id}/ambient_light",
        json={"ambient_light": level},
    )
    assert r.status_code == 200, r.text


def _cb(tok_id, char, init, buffs=None):
    return {"id": tok_id, "char_id": char["id"], "name": char["name"],
            "initiative": init, "hp_current": 40, "hp_max": 40,
            "buffs": buffs or [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


async def _reseed(gm_client, pip, garrik, pip_buffs):
    """Re-seed the battle with the attacker (Pip) carrying `pip_buffs` on its
    combatant — `_get_buffs`/the resolver read combatant buffs by char_id
    (the same seeding the Relentless-Avenger move test relies on)."""
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [_cb(PIP_TOK, pip, 12, pip_buffs),
                             _cb(GAR_TOK, garrik, 8)],
              "turn_index": 0, "round": 1, "active": True},
    )


async def _visibility(gm_client, attacker, target):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/visibility",
        params={"attacker_combatant_id": attacker,
                "target_combatant_id": target},
    )
    assert r.status_code == 200, r.text
    return r.json()


@pytest_asyncio.fixture
async def vision_scene(gm_client, roster):
    """Pip (attacker) + Garrik (target) placed 1 cell apart, in a battle, on
    the active map. Restores ambient to bright + clears senses on teardown."""
    pip, garrik = roster["Pip Quickfingers"], roster["Garrik Ironside"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/place-token",
        json={"x": 350.0, "y": 350.0})
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/place-token",
        json={"x": 420.0, "y": 350.0})  # +1 cell = 5 ft
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": PIP_TOK, "char_id": pip["id"], "name": pip["name"],
             "initiative": 12, "hp_current": 30, "hp_max": 30, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": GAR_TOK, "char_id": garrik["id"], "name": garrik["name"],
             "initiative": 8, "hp_current": 50, "hp_max": 50, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    body = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")).json()
    map_id = body["map_id"]
    try:
        yield {"pip": pip, "garrik": garrik, "map_id": map_id}
    finally:
        await _set_ambient(gm_client, map_id, "bright")
        await _patch_sheet(gm_client, pip["id"],
                           {"darkvision_ft": 0, "truesight_ft": 0})


async def test_bright_ambient_seen(gm_client, vision_scene):
    """Default bright map → target is seen."""
    v = await _visibility(gm_client, PIP_TOK, GAR_TOK)
    assert v["illumination"] == "bright"
    assert v["visibility"] == "seen"
    assert v["range_ft"] == 5


async def test_dark_no_senses_unseen(gm_client, vision_scene):
    """Dark map, attacker with no special senses → target unseen."""
    await _set_ambient(gm_client, vision_scene["map_id"], "dark")
    v = await _visibility(gm_client, PIP_TOK, GAR_TOK)
    assert v["visibility"] == "unseen", v


async def test_dark_with_darkvision_obscured(gm_client, vision_scene):
    """Dark + darkvision (≥ range) → obscured (dark reads as dim; no attack
    edge). Senses ride a combatant buff (read by the resolver)."""
    sc = vision_scene
    await _reseed(gm_client, sc["pip"], sc["garrik"],
                  [{"key": "dv", "effects": {"darkvision_ft": 60}}])
    await _set_ambient(gm_client, sc["map_id"], "dark")
    v = await _visibility(gm_client, PIP_TOK, GAR_TOK)
    assert int(v["senses"].get("darkvision_ft") or 0) == 60, v
    assert v["visibility"] == "obscured", v
    assert v["illumination"] == "dim", v


async def test_darkvision_beyond_range_unseen(gm_client, vision_scene):
    """Darkvision shorter than the range doesn't help → still unseen."""
    sc = vision_scene
    await _reseed(gm_client, sc["pip"], sc["garrik"],
                  [{"key": "dv", "effects": {"darkvision_ft": 0}}])
    await _set_ambient(gm_client, sc["map_id"], "dark")
    # range is 5 ft; with no usable darkvision the dark target stays unseen.
    v = await _visibility(gm_client, PIP_TOK, GAR_TOK)
    assert v["visibility"] == "unseen", v


async def test_dark_with_truesight_seen(gm_client, vision_scene):
    """Dark + truesight (≥ range) → seen regardless of light."""
    sc = vision_scene
    await _reseed(gm_client, sc["pip"], sc["garrik"],
                  [{"key": "ts", "effects": {"truesight_ft": 60}}])
    await _set_ambient(gm_client, sc["map_id"], "dark")
    v = await _visibility(gm_client, PIP_TOK, GAR_TOK)
    assert int(v["senses"].get("truesight_ft") or 0) == 60, v
    assert v["visibility"] == "seen", v


async def test_dark_with_devils_sight_seen(gm_client, vision_scene):
    """Dark + Devil's Sight (sees_in_darkness) → magical dark reads as
    bright → seen."""
    sc = vision_scene
    await _reseed(gm_client, sc["pip"], sc["garrik"],
                  [{"key": "ds", "effects": {"sees_in_darkness": True}}])
    await _set_ambient(gm_client, sc["map_id"], "dark")
    v = await _visibility(gm_client, PIP_TOK, GAR_TOK)
    assert v["senses"].get("sees_in_darkness") is True, v
    assert v["visibility"] == "seen", v


async def test_dark_target_lit_seen(gm_client, vision_scene):
    """Dark map but the target carries its own light → its square is bright →
    seen even to a senseless attacker."""
    await _set_ambient(gm_client, vision_scene["map_id"], "dark")
    # Light the target's own square (a torch on Garrik).
    body = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")).json()
    gar_tok = next(t for t in body["tokens"]
                   if t.get("character_id") == vision_scene["garrik"]["id"])
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/token/{gar_tok['id']}",
        json={"light_bright_ft": 20})
    v = await _visibility(gm_client, PIP_TOK, GAR_TOK)
    assert v["illumination"] == "bright", v
    assert v["visibility"] == "seen", v
