"""v2.195.0 — Potion of Climbing (RAW DMG p.187, common): drink → a
climbing speed equal to your walking speed + advantage on Strength
(Athletics) checks to climb, for 1 hour, no concentration.

The sixth self-buff potion. Its `climbing` buff carries
`advantage_on: ["str_check"]`, which the generalized STR-check-advantage
reader (rage-only until v2.192.0) honours. This file proves the
mechanical half end-to-end: Garrik drinks Climbing, then a STR ability
check rolled via `/roll` swaps 1d20 → 2d20kh1 (advantage). The climbing
speed itself is GM-narrated (no climb-speed numeric is tracked).

Mirrors `test_potion_of_growth.py` but exercises the STR-*check* path via
the `/roll` endpoint (stat_key="str_check") rather than the STR-*save*
path via a spell. Garrik is a Fighter with no innate STR-check
advantage, so Climbing is the sole source — a clean control.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _sheet(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    return (r.json() or {}).get("sheet") or {}


def _climbing_index(inventory):
    for i, it in enumerate(inventory):
        if isinstance(it, dict) and (it.get("_slug") or "") == (
            "potion-of-climbing"
        ):
            return i
    return -1


def _tok(char):
    return {
        "id": f"tok_climb_{char['id']}",
        "char_id": char["id"], "name": char["name"],
        "initiative": 10, "hp_current": 60, "hp_max": 60,
        "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


def _last_roll(gm_ws):
    msgs = gm_ws.buffered("roll")
    return msgs[-1] if msgs else None


async def _roll_str_check(gm_client, garrik):
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20",
            "character_id": garrik["id"],
            "stat_key": "str_check",
            "note": "Athletics (climb)",
        },
    )


@pytest_asyncio.fixture
async def battle_garrik(gm_client, roster):
    garrik = roster["Garrik Ironside"]
    garrik_sheet = await _sheet(gm_client, garrik["id"])
    inv = list(garrik_sheet.get("inventory") or [])
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [_tok(garrik)],
              "turn_index": 0, "round": 1, "active": True},
    )
    try:
        yield garrik, inv
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/sheet-fields",
            json={"inventory": inv},
        )
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={"combatants": [], "turn_index": 0, "round": 1,
                  "active": False},
        )


async def test_climbing_grants_advantage_on_str_check(
    gm_client, gm_ws, battle_garrik,
):
    """Garrik drinks Potion of Climbing → a STR ability check rolls
    2d20kh1 (advantage on Athletics checks to climb)."""
    garrik, inv = battle_garrik
    idx = _climbing_index(inv)
    assert idx >= 0, "Garrik must carry a Potion of Climbing"

    drink = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/use_item_action",
        json={"inventory_index": idx, "action_key": "drink"},
    )
    assert drink.status_code == 200, drink.text
    body = drink.json()
    assert body["buff_key"] == "climbing", body
    assert body["buff_installed"] is True, body

    gm_ws.mark()
    resp = await _roll_str_check(gm_client, garrik)
    assert resp.status_code == 200, resp.text

    rr = _last_roll(gm_ws)
    assert rr is not None, "expected a roll broadcast for Garrik's STR check"
    assert rr["data"]["expression"] == "2d20kh1", (
        f"Climbing should grant advantage on STR checks; got "
        f"{rr['data']['expression']!r}"
    )


async def test_no_climbing_str_check_is_plain(
    gm_client, gm_ws, battle_garrik,
):
    """Control: without Climbing, Garrik's STR check rolls plain 1d20 —
    proving the advantage comes from the potion, not something innate."""
    garrik, _inv = battle_garrik
    gm_ws.mark()
    resp = await _roll_str_check(gm_client, garrik)
    assert resp.status_code == 200, resp.text

    rr = _last_roll(gm_ws)
    assert rr is not None
    assert rr["data"]["expression"] == "1d20", (
        f"un-climbing Garrik should have no STR-check advantage; got "
        f"{rr['data']['expression']!r}"
    )
