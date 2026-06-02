"""v2.99.27 — Polearm Master enter-reach OA — RAW polearm-wielding gate.

RAW (PHB p.168): Polearm Master's enter-reach OA requires "you are
wielding a glaive, halberd, pike, quarterstaff, or spear." The
v2.66.4 wire detected the feat by slug but did NOT gate on the
actually-equipped weapon. v2.99.27 closes the gap: the sheet-driven
path of `_combatant_has_polearm_master` now also calls
`_pc_wields_polearm` which scans the sheet's inventory for an
`equipped: True` item whose name or `_slug` matches one of
`_POLEARM_WEAPON_NAMES = {glaive, halberd, quarterstaff, spear, pike}`.

The explicit combatant-level `polearm_master` override (used by
existing v2.66.4 tests + GM fixture setup) still wins and bypasses
both the feat AND wielding gates. This preserves the v2.66.4 test
fixtures while tightening the production gate.

Demo fixture: Garrik Ironside (Variant Human Champion Fighter Lv 9).
v2.99.27 adds:
  - Polearm Master feat (via Lv 4 ASI replacement — RAW-legal)
  - Glaive in his attacks list + inventory (default `equipped: False`)
  - Garrik becomes the demo's two-feat Fighter (Lucky + Polearm
    Master). Tests flip the Glaive's `equipped` field via
    sheet-fields PATCH to gate the trigger.

Tests:
  - Glaive equipped → enter-reach OA fires for Garrik.
  - Glaive NOT equipped (default) → enter-reach OA does NOT fire,
    even though Garrik has the feat (RAW-correct).
"""
import asyncio
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _tok(char, init=10, hp=60):
    return {
        "id": f"tok_pmw_{char['id']}",
        "char_id": char["id"],
        "name": char["name"],
        "initiative": init,
        "hp_current": hp,
        "hp_max": hp,
        "buffs": [],
        "economy": {
            "action": False, "bonus": False, "reaction": False, "movement": 0,
        },
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


async def _place_token(gm_client, char_id, x, y):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/place-token",
        json={"x": float(x), "y": float(y)},
    )
    assert r.status_code == 200, r.text


async def _get_token_for_char(gm_client, char_id):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")
    assert r.status_code == 200
    for t in r.json().get("tokens", []):
        if t.get("character_id") == char_id:
            return t
    return None


async def _set_glaive_equipped(gm_client, char_id, equipped: bool):
    """Flip Garrik's Glaive `equipped` field via sheet-fields PATCH.
    Mutates the inventory entry whose `_slug` is "glaive".
    """
    # Fetch the existing inventory first to preserve other items.
    # sheet-fields PATCH supports partial deep-merge for `inventory`
    # via setting the whole array — fetch via the roster + inventory
    # endpoint isn't available, so we just send the Glaive's full
    # new state nested by index isn't supported either.
    # Simplest: send the full inventory list with just the Glaive's
    # `equipped` updated. But we don't have read access to the
    # inventory. Workaround: use the sheet `attacks` array driver
    # since `_pc_wields_polearm` reads `inventory` only.
    # Send a minimal inventory list that contains ONLY the Glaive
    # with the desired `equipped` state. This wipes other items
    # temporarily — fine for a focused test.
    return await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={
            "inventory": [
                {"name": "Glaive", "type": "weapon", "qty": 1,
                 "equippable": True, "equipped": equipped, "hands": 2,
                 "damage": "1d10", "damage_type": "slashing",
                 "range": "10 ft", "properties": "heavy, two-handed, reach",
                 "_slug": "glaive"},
            ],
        },
    )


def _oa_broadcasts(gm_ws) -> list:
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "opportunity-attack-trigger"
    ]


async def test_polearm_master_fires_when_glaive_equipped(
    gm_client, gm_ws, roster,
):
    """Garrik has Polearm Master + Glaive equipped via sheet-fields
    PATCH. Krieger moves from 15 ft → 10 ft (enter-reach transition
    on a glaive's 10-ft reach). Enter-reach OA fires for Garrik.
    """
    garrik = roster["Garrik Ironside"]
    krieger = roster["Krieger Stonefist"]
    # Equip the Glaive.
    r = await _set_glaive_equipped(gm_client, garrik["id"], True)
    assert r.status_code == 200, r.text

    garrik_combatant = _tok(garrik, init=8)
    # Set reach explicitly to 10 ft via the override field so the
    # token-move reach calc doesn't depend on the wire's attack-list
    # derivation. The Polearm Master gate itself is what we're
    # testing.
    garrik_combatant["melee_reach_ft"] = 10.0
    await _seed_battle(gm_client, [
        _tok(krieger, init=10),
        garrik_combatant,
    ])

    await _place_token(gm_client, garrik["id"], 350.0, 350.0)
    await _place_token(gm_client, krieger["id"], 560.0, 350.0)  # 3 cells = 15 ft
    kr_tok = await _get_token_for_char(gm_client, krieger["id"])
    assert kr_tok, "Krieger token must exist"
    await asyncio.sleep(0.15)
    gm_ws.mark()

    # Move Krieger 1 cell closer → 10 ft from Garrik. Enter-reach.
    # oa_confirmed=True bypasses the v2.99.55 pre-move 409 gate.
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{kr_tok['id']}/move",
        json={"x": 490.0, "y": 350.0, "oa_confirmed": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    matching = [
        t for t in (data.get("opportunity_attack_triggers") or [])
        if t.get("watcher_char_id") == garrik["id"]
           and t.get("trigger_type") == "enter"
    ]
    assert matching, (
        f"expected enter-reach OA trigger for Garrik when Glaive is "
        f"equipped; got {data.get('opportunity_attack_triggers')}"
    )


async def test_polearm_master_skips_when_no_polearm_equipped(
    gm_client, gm_ws, roster,
):
    """Control: Garrik has Polearm Master feat but Glaive is NOT
    equipped (default from demo seed). The v2.99.27 wielding gate
    short-circuits the enter-reach OA — RAW only fires when actually
    wielding a polearm.
    """
    garrik = roster["Garrik Ironside"]
    krieger = roster["Krieger Stonefist"]
    # Ensure Glaive is unequipped (default).
    r = await _set_glaive_equipped(gm_client, garrik["id"], False)
    assert r.status_code == 200, r.text

    garrik_combatant = _tok(garrik, init=8)
    garrik_combatant["melee_reach_ft"] = 10.0
    await _seed_battle(gm_client, [
        _tok(krieger, init=10),
        garrik_combatant,
    ])

    await _place_token(gm_client, garrik["id"], 350.0, 350.0)
    await _place_token(gm_client, krieger["id"], 560.0, 350.0)
    kr_tok = await _get_token_for_char(gm_client, krieger["id"])
    assert kr_tok
    await asyncio.sleep(0.15)
    gm_ws.mark()

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{kr_tok['id']}/move",
        json={"x": 490.0, "y": 350.0},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    matching = [
        t for t in (data.get("opportunity_attack_triggers") or [])
        if t.get("watcher_char_id") == garrik["id"]
           and t.get("trigger_type") == "enter"
    ]
    assert not matching, (
        f"enter-reach OA should NOT fire when Garrik isn't wielding a "
        f"polearm (RAW gate); got {data.get('opportunity_attack_triggers')}"
    )
