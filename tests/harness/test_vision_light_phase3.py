"""v2.708.0 — Vision & Light Phase 3 (docs/plans/vision-and-light.md).

Spell-placed light/darkness/obscurement emitters:
  - `POST /api/campaign/{cid}/light_emitter` {kind, x, y, radius_ft} places a
    `darkness` (magical dark), `daylight` (bright), or `fog` (heavy
    obscurement) emitter; `DELETE .../light_emitter/{id}` clears it.
  - `_illumination_at_point` reads them (precedence fog > daylight > darkness)
    and `_visibility_between` applies the RAW sense rules:
      * Darkness → only Devil's Sight (`sees_in_darkness`) / truesight pierces
        (darkvision does NOT — PHB p.230);
      * Daylight → bright (dispels darkness);
      * Fog → only truesight / blindsight see through.

Validated via the read-only `/visibility` resolver. Attacker Pip, target
Garrik 5 ft apart; the emitter is centered on Garrik.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

PIP_TOK = "tok_v3_pip"
GAR_TOK = "tok_v3_gar"
GAR_X, GAR_Y = 420.0, 350.0
_DV = [{"key": "dv", "name": "Darkvision", "effects": {"darkvision_ft": 60}}]
_DS = [{"key": "ds", "name": "Devil's Sight", "effects": {"sees_in_darkness": True}}]
_TS = [{"key": "ts", "name": "Truesight", "effects": {"truesight_ft": 60}}]


def _cb(tok_id, char, init, buffs=None):
    return {"id": tok_id, "char_id": char["id"], "name": char["name"],
            "initiative": init, "hp_current": 40, "hp_max": 40,
            "buffs": buffs or [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


async def _seed(gm_client, pip, garrik, pip_buffs=None):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [_cb(PIP_TOK, pip, 20, pip_buffs),
                             _cb(GAR_TOK, garrik, 8)],
              "turn_index": 0, "round": 1, "active": True})


async def _place(gm_client, kind, radius_ft=15.0, x=GAR_X, y=GAR_Y):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/light_emitter",
        json={"kind": kind, "x": x, "y": y, "radius_ft": radius_ft})
    assert r.status_code == 200, r.text
    return r.json()["emitter"]["id"]


async def _visibility(gm_client):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/visibility",
        params={"attacker_combatant_id": PIP_TOK,
                "target_combatant_id": GAR_TOK})
    assert r.status_code == 200, r.text
    return r.json()


async def _clear_emitters(gm_client):
    body = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")).json()
    for e in body.get("light_emitters") or []:
        await gm_client.delete(
            f"/api/campaign/{CAMPAIGN_ID}/light_emitter/{e['id']}")


@pytest_asyncio.fixture
async def scene(gm_client, roster):
    """Pip + Garrik placed 5 ft apart on the active map. Clears emitters +
    resets ambient/battle on teardown so module-level emitter state never
    leaks (this container is also the public demo)."""
    pip, garrik = roster["Pip Quickfingers"], roster["Garrik Ironside"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/place-token",
        json={"x": 350.0, "y": 350.0})
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/place-token",
        json={"x": GAR_X, "y": GAR_Y})
    map_id = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/tokens")).json()["map_id"]
    await _clear_emitters(gm_client)
    try:
        yield {"pip": pip, "garrik": garrik, "map_id": map_id}
    finally:
        await _clear_emitters(gm_client)
        await gm_client.post(
            f"/campaign/{CAMPAIGN_ID}/settings/maps/{map_id}/ambient_light",
            json={"ambient_light": "bright"})
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={"combatants": [], "turn_index": 0, "round": 1,
                  "active": False})


async def test_darkness_blocks_darkvision(gm_client, scene):
    """A Darkness sphere over the target → a darkvision attacker still can't
    see it (magical darkness; darkvision doesn't pierce)."""
    await _seed(gm_client, scene["pip"], scene["garrik"], pip_buffs=list(_DV))
    await _place(gm_client, "darkness")
    v = await _visibility(gm_client)
    assert v["illumination"] == "magical_dark", v
    assert v["visibility"] == "unseen", v


async def test_darkness_pierced_by_devils_sight(gm_client, scene):
    """Devil's Sight (sees_in_darkness) pierces magical darkness → seen."""
    await _seed(gm_client, scene["pip"], scene["garrik"], pip_buffs=list(_DS))
    await _place(gm_client, "darkness")
    v = await _visibility(gm_client)
    assert v["visibility"] == "seen", v


async def test_daylight_lights_dark_map(gm_client, scene):
    """A Daylight emitter on a dark map → the target's square is bright →
    seen even to a senseless attacker."""
    await _seed(gm_client, scene["pip"], scene["garrik"], pip_buffs=[])
    await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings/maps/{scene['map_id']}/ambient_light",
        json={"ambient_light": "dark"})
    await _place(gm_client, "daylight", radius_ft=30.0)
    v = await _visibility(gm_client)
    assert v["illumination"] == "bright", v
    assert v["visibility"] == "seen", v


async def test_fog_blocks_darkvision(gm_client, scene):
    """Fog Cloud (heavy obscurement) → a darkvision attacker can't see in →
    unseen."""
    await _seed(gm_client, scene["pip"], scene["garrik"], pip_buffs=list(_DV))
    await _place(gm_client, "fog")
    v = await _visibility(gm_client)
    assert v["illumination"] == "fog", v
    assert v["visibility"] == "unseen", v


async def test_fog_pierced_by_truesight(gm_client, scene):
    """Truesight sees through fog → seen."""
    await _seed(gm_client, scene["pip"], scene["garrik"], pip_buffs=list(_TS))
    await _place(gm_client, "fog")
    v = await _visibility(gm_client)
    assert v["visibility"] == "seen", v


async def test_place_bad_kind_400(gm_client, scene):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/light_emitter",
        json={"kind": "rainbow", "x": GAR_X, "y": GAR_Y, "radius_ft": 15})
    assert r.status_code == 400, r.text


async def test_place_bad_radius_400(gm_client, scene):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/light_emitter",
        json={"kind": "fog", "x": GAR_X, "y": GAR_Y, "radius_ft": 0})
    assert r.status_code == 400, r.text


async def test_remove_unknown_404(gm_client, scene):
    r = await gm_client.delete(
        f"/api/campaign/{CAMPAIGN_ID}/light_emitter/lem_nope")
    assert r.status_code == 404, r.text


async def test_non_gm_cannot_place(alice_client, scene):
    r = await alice_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/light_emitter",
        json={"kind": "darkness", "x": GAR_X, "y": GAR_Y, "radius_ft": 15})
    assert r.status_code == 403, r.text
