"""Opportunity attacks are enforced on GRIDLESS maps too.

Every other OA test runs on the square-grid demo campaign. Gridless maps use
Euclidean distance (``_distance_ft_between_points`` picks it for any non-square
grid_type); this guards that the full enforcement chain — preview flag, the 409
`oa_confirmation_required` gate on an unconfirmed move, and the trigger list on a
confirmed move — all fire when the map's grid_type is ``none``.
"""
import asyncio

import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _make_combatant(name, char_id, init=10, hp=40):
    return {
        "id": f"tok_gl_{char_id}", "char_id": char_id, "name": name,
        "initiative": init, "hp_current": hp, "hp_max": hp, "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
    }


@pytest_asyncio.fixture
async def gridless_map(gm_client):
    """Flip the active map to gridless for the test, restore to square after."""
    am = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/active-map")).json()
    mid = am["map_id"]
    await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/grid_type",
        json={"grid_type": "none"})
    try:
        yield mid
    finally:
        await gm_client.post(
            f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/grid_type",
            json={"grid_type": "square"})


async def _place(gm_client, char_id, x, y):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/place-token",
        json={"x": float(x), "y": float(y)})
    assert r.status_code == 200, r.text


async def _token_for(gm_client, char_id):
    toks = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")).json()["tokens"]
    return next((t for t in toks if t.get("character_id") == char_id), None)


async def test_oa_enforced_on_gridless_map(gm_client, roster, gridless_map):
    krieger = roster["Krieger Stonefist"]
    tavik = roster["Brother Tavik Stonebrow"]
    await gm_client.put(f"/api/campaign/{CAMPAIGN_ID}/battle", json={
        "combatants": [
            _make_combatant(krieger["name"], krieger["id"], init=10),
            _make_combatant(tavik["name"], tavik["id"], init=8),
        ], "turn_index": 0, "round": 1, "active": True})
    # Krieger 5 ft (70 px) from Tavik → within reach.
    await _place(gm_client, krieger["id"], 350.0, 350.0)
    await _place(gm_client, tavik["id"], 420.0, 350.0)
    kr = await _token_for(gm_client, krieger["id"])
    assert kr, "Krieger token must exist"
    await asyncio.sleep(0.1)

    # Preview flags the OA (Euclidean distance on the gridless map).
    pv = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{kr['id']}/preview_move",
        json={"x": 700.0, "y": 350.0})
    assert pv.status_code == 200, pv.text
    assert pv.json().get("would_trigger_oa") is True, pv.json()
    assert pv.json().get("distance_ft") == 25.0, pv.json()

    # Enforcement gate: an UNCONFIRMED move out of reach is blocked with 409.
    blocked = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{kr['id']}/move",
        json={"x": 700.0, "y": 350.0})
    assert blocked.status_code == 409, blocked.text
    assert blocked.json().get("error") == "oa_confirmation_required", blocked.json()

    # Confirmed move goes through and reports the trigger naming Tavik.
    ok = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{kr['id']}/move",
        json={"x": 700.0, "y": 350.0, "oa_confirmed": True})
    assert ok.status_code == 200, ok.text
    triggers = [t for t in (ok.json().get("opportunity_attack_triggers") or [])
                if t.get("watcher_char_id") == tavik["id"]]
    assert triggers, ok.json().get("opportunity_attack_triggers")


async def test_no_oa_on_gridless_when_move_stays_in_reach(gm_client, roster, gridless_map):
    """Control: a move that keeps the mover within 5 ft doesn't provoke."""
    krieger = roster["Krieger Stonefist"]
    tavik = roster["Brother Tavik Stonebrow"]
    await gm_client.put(f"/api/campaign/{CAMPAIGN_ID}/battle", json={
        "combatants": [
            _make_combatant(krieger["name"], krieger["id"], init=10),
            _make_combatant(tavik["name"], tavik["id"], init=8),
        ], "turn_index": 0, "round": 1, "active": True})
    await _place(gm_client, krieger["id"], 350.0, 350.0)
    await _place(gm_client, tavik["id"], 420.0, 350.0)
    kr = await _token_for(gm_client, krieger["id"])
    await asyncio.sleep(0.1)
    # Shuffle 20 px (still < 5 ft from Tavik) → no OA, no 409.
    ok = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{kr['id']}/move",
        json={"x": 360.0, "y": 350.0})
    assert ok.status_code == 200, ok.text
    triggers = [t for t in (ok.json().get("opportunity_attack_triggers") or [])
                if t.get("watcher_char_id") == tavik["id"]]
    assert not triggers, ok.json().get("opportunity_attack_triggers")


async def test_oa_large_watcher_reach_is_edge_aware(gm_client, roster, gridless_map):
    """v2.957.0 — a size-2 monster threatens a hero whose CENTER is 7.5 ft away
    (edges ~2.5 ft apart) with only a 5 ft weapon. Pre-fix the center-to-center
    7.5 ft read as outside 5 ft reach → the monster's OA never fired. Edge-aware
    reach (5 + 2.5 for the size-2 watcher) fixes it."""
    krieger = roster["Krieger Stonefist"]
    templates = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")).json()
    bandit = next((t for t in templates if "bandit" in t["name"].lower()), templates[0])

    async def _run(watcher_size):
        tok = (await gm_client.post(f"/api/campaign/{CAMPAIGN_ID}/tokens", json={
            "token_template_id": bandit["id"], "label": f"Watcher{watcher_size}",
            "x": 350.0, "y": 350.0, "color": "#7a9", "size": watcher_size})).json()
        await gm_client.put(f"/api/campaign/{CAMPAIGN_ID}/battle", json={
            "combatants": [
                _make_combatant(krieger["name"], krieger["id"], init=10),
                {"id": "tok_watch", "char_id": None, "source_token_id": tok["id"],
                 "token_template_id": bandit["id"], "name": f"Watcher{watcher_size}",
                 "initiative": 8, "hp_current": 50, "hp_max": 50, "buffs": [],
                 "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
            ], "turn_index": 0, "round": 1, "active": True})
        # place-token SNAPS to a cell; use /move (raw, no snap) to put Krieger's
        # center exactly 105 px (7.5 ft) from the watcher center.
        await _place(gm_client, krieger["id"], 350.0, 350.0)
        kr = await _token_for(gm_client, krieger["id"])
        await gm_client.post(f"/api/campaign/{CAMPAIGN_ID}/token/{kr['id']}/move",
                             json={"x": 455.0, "y": 350.0, "oa_confirmed": True})
        ok = await gm_client.post(f"/api/campaign/{CAMPAIGN_ID}/token/{kr['id']}/move",
                                  json={"x": 700.0, "y": 350.0, "oa_confirmed": True})
        assert ok.status_code == 200, ok.text
        return [t for t in (ok.json().get("opportunity_attack_triggers") or [])
                if t.get("watcher_combatant_id") == "tok_watch"]

    # Size-2 watcher: edge-aware reach 7.5 ft covers the 7.5 ft center gap → OA.
    assert await _run(2), "size-2 watcher should provoke at 7.5 ft center distance"
    # Control — size-1 watcher: base 5 ft reach, 7.5 ft > 5 ft → no OA.
    assert not await _run(1), "size-1 watcher should NOT provoke at 7.5 ft"
