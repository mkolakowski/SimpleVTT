"""v2.192.0 — Potion of Growth (RAW DMG p.187, uncommon): drink → the
enlarge effect for up to 1d4 hours, no concentration. RAW (PHB p.237)
enlarge grants advantage on STR checks and STR saving throws (plus +1d4
weapon damage and size Large, both GM-narrated here).

The fifth self-buff potion. Its `growth` buff carries
`advantage_on: ["str_check", "str_save"]`, and v2.192.0 generalized the
STR-advantage readers (rage-only until now) so any marker-bearing buff
composes. This file proves the mechanical half end-to-end: Garrik drinks
Growth, then a STR-save spell aimed at him rolls 2d20kh1 (advantage).

Mirrors `test_rage_str_save.py`: Thalindra casts Gust of Wind (Wizard L2,
STR save) at Garrik; the save-roll construction swaps 1d20 → 2d20kh1 when
the target has STR-save advantage. Garrik is a Fighter with no innate
STR-save advantage, so Growth is the sole source — a clean control.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

GUST_OF_WIND_INDEX = 15  # Thalindra's STR-save spell (see test_rage_str_save)


async def _sheet(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    return (r.json() or {}).get("sheet") or {}


def _growth_index(inventory):
    for i, it in enumerate(inventory):
        if isinstance(it, dict) and (it.get("_slug") or "") == (
            "potion-of-growth"
        ):
            return i
    return -1


def _tok(char):
    return {
        "id": f"tok_grow_{char['id']}",
        "char_id": char["id"], "name": char["name"],
        "initiative": 10, "hp_current": 60, "hp_max": 60,
        "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


def _last_roll_request(gm_ws):
    msgs = gm_ws.buffered("roll_request")
    return msgs[-1] if msgs else None


async def _cast_gust_at(gm_client, thal, garrik):
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thal["id"],
            "spell_index": GUST_OF_WIND_INDEX,
            "slot_level": 2, "class_slug": "wizard",
            "target_combatant_id": f"tok_grow_{garrik['id']}",
            "target_character_id": garrik["id"],
            "target_name": garrik["name"],
            "override": True,
        },
    )


@pytest_asyncio.fixture
async def battle_thal_garrik(gm_client, roster):
    thal = roster["Thalindra Moonwhisper"]
    garrik = roster["Garrik Ironside"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thal['id']}/rest",
        json={"type": "long"},
    )
    garrik_sheet = await _sheet(gm_client, garrik["id"])
    inv = list(garrik_sheet.get("inventory") or [])
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [_tok(thal), _tok(garrik)],
              "turn_index": 0, "round": 1, "active": True},
    )
    try:
        yield thal, garrik, inv
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


async def test_growth_grants_advantage_on_str_save(
    gm_client, gm_ws, battle_thal_garrik,
):
    """Garrik drinks Potion of Growth → a STR-save spell aimed at him
    rolls 2d20kh1 (advantage from the enlarge effect)."""
    thal, garrik, inv = battle_thal_garrik
    idx = _growth_index(inv)
    assert idx >= 0, "Garrik must carry a Potion of Growth"

    drink = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/use_item_action",
        json={"inventory_index": idx, "action_key": "drink"},
    )
    assert drink.status_code == 200, drink.text
    body = drink.json()
    assert body["buff_key"] == "growth", body
    assert body["buff_installed"] is True, body

    gm_ws.mark()
    resp = await _cast_gust_at(gm_client, thal, garrik)
    assert resp.status_code == 200, resp.text
    assert resp.json()["auto_save_ability"] == "STR"

    rr = _last_roll_request(gm_ws)
    assert rr is not None, "expected a roll_request for Garrik's STR save"
    assert rr["data"]["base_expression"] == "2d20kh1", (
        f"Growth should grant advantage on STR save; got "
        f"{rr['data']['base_expression']!r}"
    )


async def test_no_growth_str_save_is_plain(
    gm_client, gm_ws, battle_thal_garrik,
):
    """Control: without Growth, Garrik's STR save rolls plain 1d20 —
    proving the advantage comes from the potion, not something innate."""
    thal, garrik, _inv = battle_thal_garrik
    gm_ws.mark()
    resp = await _cast_gust_at(gm_client, thal, garrik)
    assert resp.status_code == 200, resp.text

    rr = _last_roll_request(gm_ws)
    assert rr is not None
    assert rr["data"]["base_expression"] == "1d20", (
        f"un-grown Garrik should have no STR-save advantage; got "
        f"{rr['data']['base_expression']!r}"
    )
