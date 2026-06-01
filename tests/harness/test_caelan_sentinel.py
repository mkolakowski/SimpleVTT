"""v2.99.24 — Caelan's Sentinel feat from the sheet's `feats` list.

v2.66.5 wired the Sentinel feat's effect 3 ("when a creature within
5 ft of you attacks an ally other than you, you can use your
reaction to make a melee attack against the attacker"). The
existing v2.66.5 harness test (`test_sentinel_fires_when_ally_
attacks_target_near_watcher` in `test_opportunity_attack.py`) sets
the trigger via a combatant-level `sentinel: True` flag —
exercising the override path of `_combatant_has_sentinel`.

v2.99.24 declares the Sentinel feat on Sir Caelan Lightbringer's
Variant Human sheet (`{slug: "sentinel"}`), so the sheet-driven
path of `_combatant_has_sentinel` is now exercised by a demo PC
too. This file's tests verify that path end-to-end with no manual
combatant override.

Test:
- Krieger attacks Pip. Caelan stands within 5 ft of Krieger (the
  attacker). Assert the `sentinel_triggers` list in the /attack
  response names Caelan AND a `feature_used(source=
  sentinel-attack-trigger)` broadcast fires for him.
"""
import asyncio
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _tok(char, init=10, hp=40):
    return {
        "id": f"tok_csn_{char['id']}",
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


def _sentinel_broadcasts(gm_ws) -> list:
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "sentinel-attack-trigger"
    ]


async def test_caelan_sentinel_from_sheet_triggers_on_ally_attack(
    gm_client, gm_ws, roster,
):
    """Krieger attacks Pip; Caelan stands within 5 ft of Krieger
    (the attacker). Caelan's sheet carries the Sentinel feat
    (v2.99.24); `_combatant_has_sentinel` reads it via the sheet
    path. Assert the /attack response's sentinel_triggers names
    Caelan AND the broadcast fires.
    """
    krieger = roster["Krieger Stonefist"]
    pip = roster["Pip Quickfingers"]
    caelan = roster["Sir Caelan Lightbringer"]

    await _seed_battle(gm_client, [
        _tok(krieger, init=12),
        _tok(pip, init=10),
        _tok(caelan, init=8),
    ])

    # Krieger at origin; Pip 5 ft south (within Greataxe reach);
    # Caelan 5 ft east of Krieger (within 5 ft of attacker —
    # Sentinel effect 3 condition).
    await _place_token(gm_client, krieger["id"], 350.0, 350.0)
    await _place_token(gm_client, pip["id"], 350.0, 420.0)
    await _place_token(gm_client, caelan["id"], 420.0, 350.0)
    await asyncio.sleep(0.15)
    gm_ws.mark()

    pip_combatant_id = f"tok_csn_{pip['id']}"
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": krieger["id"],
            "attack_index": 0,  # Greataxe
            "target_combatant_id": pip_combatant_id,
            "override": True,
            "override_range": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    triggers = [
        t for t in (data.get("sentinel_triggers") or [])
        if t.get("watcher_char_id") == caelan["id"]
    ]
    assert triggers, (
        f"expected Sentinel trigger naming Caelan; got "
        f"sentinel_triggers={data.get('sentinel_triggers')}"
    )

    await asyncio.sleep(0.2)
    sentinel_msgs = _sentinel_broadcasts(gm_ws)
    caelan_msgs = [
        m for m in sentinel_msgs
        if (m.get("data") or {}).get("character_id") == caelan["id"]
    ]
    assert caelan_msgs, (
        f"expected sentinel-attack-trigger broadcast for Caelan; "
        f"got: {[(m.get('data') or {}).get('character_name') for m in sentinel_msgs]}"
    )
