"""v2.899.0 — embedded doors (Phase 1: data + server).

A wall keeps its single segment and carries a ``doors`` list of openings
``{id, t0, t1, open, ...}`` (t0<t1 fractions along the wall). A CLOSED embedded
door still blocks line of sight; toggling it OPEN carves a real gap in the wall
(``_wall_solid_spans``). Toggled via a composite ``{wallId}:{doorId}`` id.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

PIP = "tok_emb_pip"
GAR = "tok_emb_gar"


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
async def emb_scene(gm_client, roster):
    pip, garrik = roster["Pip Quickfingers"], roster["Garrik Ironside"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/place-token",
        json={"x": 350.0, "y": 350.0})
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/place-token",
        json={"x": 420.0, "y": 350.0})
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [_cb(PIP, pip, 12), _cb(GAR, garrik, 8)],
              "turn_index": 0, "round": 1, "active": True})
    mid = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")).json()["map_id"]
    # A vertical wall across the sight line (y=350 → t≈0.5) with a CLOSED
    # embedded door covering the middle.
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls",
        json={"walls": [{"id": "embwall", "x1": 385, "y1": 300, "x2": 385, "y2": 400,
                         "doors": [{"id": "d1", "t0": 0.3, "t1": 0.7, "open": False}]}]})
    try:
        yield {"map_id": mid}
    finally:
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})


async def test_embedded_door_round_trips(gm_client, emb_scene):
    mid = emb_scene["map_id"]
    walls = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls")).json()["walls"]
    w = next(w for w in walls if w["id"] == "embwall")
    assert w["doors"][0]["id"] == "d1", w
    assert w["doors"][0]["t0"] == 0.3 and w["doors"][0]["t1"] == 0.7, w
    assert w["doors"][0]["open"] is False, w


async def test_embedded_door_toggle_changes_line_of_sight(gm_client, emb_scene):
    mid = emb_scene["map_id"]
    # Closed embedded door → the wall is fully solid → blocked ("unseen").
    # (Whether an UNblocked target reads "seen" vs "obscured" depends on the
    # map's ambient light, so we only assert blocked-vs-not here.)
    assert await _visibility(gm_client, PIP, GAR) == "unseen"
    # Open it (composite id) → a gap opens → sight is no longer blocked.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/door/embwall:d1/toggle")
    assert r.status_code == 200 and r.json()["open"] is True, r.text
    assert await _visibility(gm_client, PIP, GAR) != "unseen"
    # Close again → blocked again.
    r2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/door/embwall:d1/toggle")
    assert r2.json()["open"] is False
    assert await _visibility(gm_client, PIP, GAR) == "unseen"


async def test_embedded_door_unknown_id_404(gm_client, emb_scene):
    mid = emb_scene["map_id"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/door/embwall:nope/toggle")
    assert r.status_code == 404, r.text


async def test_embedded_door_bad_span_dropped(gm_client, emb_scene):
    mid = emb_scene["map_id"]
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls",
        json={"walls": [{"id": "w2", "x1": 0, "y1": 0, "x2": 100, "y2": 0,
                         "doors": [{"id": "good", "t0": 0.2, "t1": 0.6},
                                   {"id": "bad", "t0": 0.8, "t1": 0.4}]}]})
    walls = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls")).json()["walls"]
    w = next(w for w in walls if w["id"] == "w2")
    ids = [d["id"] for d in w.get("doors", [])]
    assert "good" in ids and "bad" not in ids, w  # inverted span dropped
