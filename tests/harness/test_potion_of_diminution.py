"""v2.199.0 — Potion of Diminution (RAW DMG p.187, rare): drink → the
"reduce" effect of enlarge/reduce for up to 1d4 hours, no concentration —
size one smaller, DISadvantage on STR checks and STR saving throws, and
weapon attacks deal -1d4.

The eighth self-buff potion and the first DEbuff one — the mirror image of
Potion of Growth. Its `diminution` buff carries
`disadvantage_on: ["str_check", "str_save"]`, honoured by the v2.199.0
STR-check disadvantage intercept in `/roll`. This file proves the
mechanical half end-to-end: Garrik drinks Diminution, then a STR ability
check rolled via `/roll` swaps 1d20 → 2d20kl1 (disadvantage). The size
reduction and the -1d4 weapon damage stay GM-narrated.

Mirrors `test_potion_of_climbing.py` but on the inverse marker — Garrik is
a Fighter with no innate STR-check (dis)advantage, so the potion is the
sole source, giving a clean control.
"""
import re

import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _dice_part(expr: str) -> str:
    """Leading dice token, stripped of trailing modifiers — Garrik's
    Stone of Good Luck adds a +1 check bonus, so assert on the
    advantage/disadvantage dice mechanic, not the exact string.
    See BUGS.md B18 class 6."""
    m = re.match(r"^\s*(\d+d\d+(?:kh1|kl1)?)", str(expr))
    return m.group(1) if m else str(expr)


async def _sheet(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    return (r.json() or {}).get("sheet") or {}


def _diminution_index(inventory):
    for i, it in enumerate(inventory):
        if isinstance(it, dict) and (it.get("_slug") or "") == (
            "potion-of-diminution"
        ):
            return i
    return -1


def _tok(char):
    return {
        "id": f"tok_dim_{char['id']}",
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
            "note": "Athletics",
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


async def test_diminution_imposes_disadvantage_on_str_check(
    gm_client, gm_ws, battle_garrik,
):
    """Garrik drinks Potion of Diminution → a STR ability check rolls
    2d20kl1 (disadvantage on Strength checks)."""
    garrik, inv = battle_garrik
    idx = _diminution_index(inv)
    assert idx >= 0, "Garrik must carry a Potion of Diminution"

    drink = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/use_item_action",
        json={"inventory_index": idx, "action_key": "drink"},
    )
    assert drink.status_code == 200, drink.text
    body = drink.json()
    assert body["buff_key"] == "diminution", body
    assert body["buff_installed"] is True, body

    gm_ws.mark()
    resp = await _roll_str_check(gm_client, garrik)
    assert resp.status_code == 200, resp.text

    rr = _last_roll(gm_ws)
    assert rr is not None, "expected a roll broadcast for Garrik's STR check"
    assert _dice_part(rr["data"]["expression"]) == "2d20kl1", (
        f"Diminution should impose disadvantage on STR checks; got "
        f"{rr['data']['expression']!r}"
    )


async def test_no_diminution_str_check_is_plain(
    gm_client, gm_ws, battle_garrik,
):
    """Control: without Diminution, Garrik's STR check rolls plain 1d20 —
    proving the disadvantage comes from the potion, not something innate."""
    garrik, _inv = battle_garrik
    gm_ws.mark()
    resp = await _roll_str_check(gm_client, garrik)
    assert resp.status_code == 200, resp.text

    rr = _last_roll(gm_ws)
    assert rr is not None
    assert _dice_part(rr["data"]["expression"]) == "1d20", (
        f"un-reduced Garrik should have no STR-check disadvantage; got "
        f"{rr['data']['expression']!r}"
    )
