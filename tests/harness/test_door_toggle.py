"""v2.755.0 — Maps 2.0 door open/close toggle.

`POST /api/campaign/{cid}/map/{map_id}/door/{door_id}/toggle` (any member)
flips a door segment's `open` flag, persists, and broadcasts `walls_update`.
A closed door blocks line of sight (`_walls_block_sight`); opening it restores
sight — verified end-to-end through `GET /visibility`.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

PIP_TOK = "tok_door_pip"
GAR_TOK = "tok_door_gar"


def _cb(tok_id, char, init):
    return {"id": tok_id, "char_id": char["id"], "name": char["name"],
            "initiative": init, "hp_current": 40, "hp_max": 40, "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


async def _visibility(client, a, t):
    r = await client.get(
        f"/api/campaign/{CAMPAIGN_ID}/visibility",
        params={"attacker_combatant_id": a, "target_combatant_id": t})
    assert r.status_code == 200, r.text
    return r.json()["visibility"]


@pytest_asyncio.fixture
async def door_scene(gm_client, roster):
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
    mid = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")).json()["map_id"]
    # A closed door across the sight line between the two tokens.
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls",
        json={"walls": [{"id": "door-los", "x1": 385, "y1": 300,
                         "x2": 385, "y2": 400, "door": True, "open": False}]})
    try:
        yield {"map_id": mid}
    finally:
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})


async def test_door_toggle_changes_line_of_sight(gm_client, door_scene):
    mid = door_scene["map_id"]
    # Closed door → blocked.
    assert await _visibility(gm_client, PIP_TOK, GAR_TOK) == "unseen"

    # Open it → sight restored.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/door/door-los/toggle")
    assert r.status_code == 200 and r.json()["open"] is True, r.text
    assert await _visibility(gm_client, PIP_TOK, GAR_TOK) == "seen"

    # Close it again → blocked again.
    r2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/door/door-los/toggle")
    assert r2.json()["open"] is False
    assert await _visibility(gm_client, PIP_TOK, GAR_TOK) == "unseen"


async def test_player_can_toggle_door(gm_client, alice_client, door_scene):
    """Doors are interactive for non-GM players too."""
    mid = door_scene["map_id"]
    r = await alice_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/door/door-los/toggle")
    assert r.status_code == 200, r.text
    assert isinstance(r.json()["open"], bool)


async def test_toggle_non_door_404(gm_client, door_scene):
    mid = door_scene["map_id"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/door/no-such-door/toggle")
    assert r.status_code == 404, r.text
