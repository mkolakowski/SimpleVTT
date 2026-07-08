"""v2.963.0 — per-door "open check": a door can require an ability/skill check
vs a DC to open. The GM sets ``check`` (a stat_key like ``"str_check"`` or a
skill name like ``"Athletics"``) + ``dc`` per door in the editor; it round-trips
through the walls sanitizer on both embedded doors and whole-segment doors.

This file covers Phase 1 (storage). The Phase 2 enforcement (the toggle rolls
the check + gates opening) lands its own tests alongside the endpoint change.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def check_map(gm_client):
    mid = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")).json()["map_id"]
    try:
        yield mid
    finally:
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})


async def _put_get(gm_client, mid, walls):
    await gm_client.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": walls})
    return (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls")).json()["walls"]


async def test_embedded_door_check_round_trips(gm_client, check_map):
    """An embedded door stores {check, dc} through the sanitizer."""
    walls = await _put_get(gm_client, check_map, [
        {"id": "cw", "x1": 385, "y1": 300, "x2": 385, "y2": 400,
         "doors": [{"id": "d1", "t0": 0.3, "t1": 0.7, "open": False,
                    "check": "Athletics", "dc": 15}]}])
    d = next(w for w in walls if w["id"] == "cw")["doors"][0]
    assert d["check"] == "Athletics", d
    assert d["dc"] == 15, d


async def test_whole_segment_door_check_round_trips(gm_client, check_map):
    """A legacy whole-segment door also stores {check, dc}."""
    walls = await _put_get(gm_client, check_map, [
        {"id": "sd", "x1": 100, "y1": 100, "x2": 100, "y2": 200,
         "door": True, "open": False, "check": "str_check", "dc": 20}])
    w = next(w for w in walls if w["id"] == "sd")
    assert w["check"] == "str_check" and w["dc"] == 20, w


async def test_dc_clamped_and_partial_ignored(gm_client, check_map):
    """DC clamps to 1–40; a check with no dc (or dc<=0) is dropped entirely
    (an incomplete gate = a free door)."""
    walls = await _put_get(gm_client, check_map, [
        {"id": "hi", "x1": 0, "y1": 0, "x2": 0, "y2": 100,
         "doors": [{"id": "over", "t0": 0.1, "t1": 0.4, "check": "Perception", "dc": 999},
                   {"id": "nodc", "t0": 0.5, "t1": 0.9, "check": "Athletics", "dc": 0}]}])
    doors = {d["id"]: d for d in next(w for w in walls if w["id"] == "hi")["doors"]}
    assert doors["over"]["dc"] == 40, doors["over"]        # clamped high
    assert "check" not in doors["nodc"], doors["nodc"]     # dc<=0 → no gate
    assert "dc" not in doors["nodc"], doors["nodc"]


async def test_no_check_is_a_free_door(gm_client, check_map):
    """A plain door (no check/dc) carries neither field — the default."""
    walls = await _put_get(gm_client, check_map, [
        {"id": "free", "x1": 0, "y1": 0, "x2": 0, "y2": 100,
         "doors": [{"id": "d", "t0": 0.2, "t1": 0.8}]}])
    d = next(w for w in walls if w["id"] == "free")["doors"][0]
    assert "check" not in d and "dc" not in d, d


# --- Phase 2: enforcement (the toggle rolls the check + gates opening) -------

async def _door_open_state(gm_client, mid, wall_id, door_id):
    walls = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls")).json()["walls"]
    w = next(w for w in walls if w["id"] == wall_id)
    return next(d for d in w["doors"] if d["id"] == door_id)["open"]


async def _set_checked_door(gm_client, mid, dc, *, check="Athletics", open=False):
    await gm_client.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": [
        {"id": "cw", "x1": 385, "y1": 300, "x2": 385, "y2": 400,
         "doors": [{"id": "d1", "t0": 0.3, "t1": 0.7, "open": open,
                    "check": check, "dc": dc}]}]})


async def test_player_passing_check_opens_door(alice_client, gm_client, roster, check_map):
    """DC 1 → any 1d20+mod clears it → the door opens, response reports the pass."""
    pip = roster["Pip Quickfingers"]
    await _set_checked_door(gm_client, check_map, 1)
    r = await alice_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/map/{check_map}/door/cw:d1/toggle",
        json={"character_id": pip["id"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["open"] is True, body
    assert body["check"]["passed"] is True, body
    assert body["check"]["dc"] == 1 and body["check"]["character_id"] == pip["id"], body
    assert await _door_open_state(gm_client, check_map, "cw", "d1") is True


async def test_player_failing_check_keeps_door_shut(alice_client, gm_client, roster, check_map):
    """DC 999 → the check always fails → the door stays closed."""
    pip = roster["Pip Quickfingers"]
    await _set_checked_door(gm_client, check_map, 999)
    r = await alice_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/map/{check_map}/door/cw:d1/toggle",
        json={"character_id": pip["id"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["open"] is False, body
    assert body["check"]["passed"] is False, body
    # Door genuinely stayed shut server-side.
    assert await _door_open_state(gm_client, check_map, "cw", "d1") is False


async def test_gm_bypasses_check(gm_client, check_map):
    """The GM is the rules authority — a DC 999 door opens for the GM with no
    check (and no character needed)."""
    await _set_checked_door(gm_client, check_map, 999)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/map/{check_map}/door/cw:d1/toggle", json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["open"] is True, body
    assert body["check"] is None, body


async def test_player_without_token_gets_400(alice_client, gm_client, check_map):
    """A checked door with no acting character → 400 (control a token first)."""
    await _set_checked_door(gm_client, check_map, 10)
    r = await alice_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/map/{check_map}/door/cw:d1/toggle", json={})
    assert r.status_code == 400, r.text


async def test_closing_a_checked_door_needs_no_check(alice_client, gm_client, roster, check_map):
    """CLOSING never rolls — a player closes an already-open checked door freely,
    even with an impossible DC."""
    await _set_checked_door(gm_client, check_map, 999, open=True)
    r = await alice_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/map/{check_map}/door/cw:d1/toggle", json={})
    assert r.status_code == 200, r.text
    assert r.json()["open"] is False, r.json()
    assert await _door_open_state(gm_client, check_map, "cw", "d1") is False
