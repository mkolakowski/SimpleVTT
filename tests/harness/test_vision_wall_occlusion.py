"""v2.753.0 — Maps 2.0 wall occlusion in the vision resolver.

A solid wall (or closed door) segment between two tokens blocks line of sight
entirely — `_visibility_between` returns `unseen` + `blocked_by_wall`, even on
a bright map. An open door doesn't block. Exercised through
`GET /api/campaign/{cid}/visibility`.

Pip (350,350) and Garrik (420,350) sit 1 cell apart on a bright map; a
vertical wall at x≈385 (y 300→400) crosses the sight line between them.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

PIP_TOK = "tok_wall_pip"
GAR_TOK = "tok_wall_gar"


def _cb(tok_id, char, init):
    return {"id": tok_id, "char_id": char["id"], "name": char["name"],
            "initiative": init, "hp_current": 40, "hp_max": 40, "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


async def _visibility(gm_client, attacker, target):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/visibility",
        params={"attacker_combatant_id": attacker, "target_combatant_id": target})
    assert r.status_code == 200, r.text
    return r.json()


async def _set_walls(gm_client, map_id, walls):
    r = await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/map/{map_id}/walls", json={"walls": walls})
    assert r.status_code == 200, r.text


@pytest_asyncio.fixture
async def wall_scene(gm_client, roster):
    pip, garrik = roster["Pip Quickfingers"], roster["Garrik Ironside"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/place-token",
        json={"x": 350.0, "y": 350.0})
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/place-token",
        json={"x": 420.0, "y": 350.0})
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [_cb(PIP_TOK, pip, 12), _cb(GAR_TOK, garrik, 8)],
              "turn_index": 0, "round": 1, "active": True})
    map_id = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")).json()["map_id"]
    try:
        yield {"map_id": map_id}
    finally:
        await _set_walls(gm_client, map_id, [])


async def test_wall_blocks_line_of_sight(gm_client, wall_scene):
    mid = wall_scene["map_id"]
    # No walls → bright map → seen.
    v = await _visibility(gm_client, PIP_TOK, GAR_TOK)
    assert v["visibility"] == "seen", v
    assert not v.get("blocked_by_wall")

    # A wall across the sight line → unseen + blocked_by_wall.
    await _set_walls(gm_client, mid, [
        {"x1": 385, "y1": 300, "x2": 385, "y2": 400}])
    v = await _visibility(gm_client, PIP_TOK, GAR_TOK)
    assert v["visibility"] == "unseen", v
    assert v.get("blocked_by_wall") is True, v


async def test_closed_door_blocks_open_door_passes(gm_client, wall_scene):
    mid = wall_scene["map_id"]
    # A closed door blocks like a wall.
    await _set_walls(gm_client, mid, [
        {"id": "d", "x1": 385, "y1": 300, "x2": 385, "y2": 400,
         "door": True, "open": False}])
    v = await _visibility(gm_client, PIP_TOK, GAR_TOK)
    assert v["visibility"] == "unseen" and v.get("blocked_by_wall"), v

    # Opening the door restores sight.
    await _set_walls(gm_client, mid, [
        {"id": "d", "x1": 385, "y1": 300, "x2": 385, "y2": 400,
         "door": True, "open": True}])
    v = await _visibility(gm_client, PIP_TOK, GAR_TOK)
    assert v["visibility"] == "seen", v
    assert not v.get("blocked_by_wall")


async def test_offset_wall_does_not_block(gm_client, wall_scene):
    """A wall that doesn't cross the sight line (above both tokens) is ignored."""
    mid = wall_scene["map_id"]
    await _set_walls(gm_client, mid, [
        {"x1": 385, "y1": 100, "x2": 385, "y2": 200}])  # well above y=350
    v = await _visibility(gm_client, PIP_TOK, GAR_TOK)
    assert v["visibility"] == "seen", v
