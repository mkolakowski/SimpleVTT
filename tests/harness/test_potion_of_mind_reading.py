"""v2.197.0 — Potion of Mind Reading (RAW DMG p.187, rare): the second
save-imposing consumable. Drinking probes a creature's mind — the target
makes a DC 13 WIS saving throw; on a failure you read its surface
thoughts — and the potion is consumed.

The handler reuses the Fire Breath per-target save loop
(`_resolve_feature_save`) without the damage roll — no HP changes, the
thought-reading itself is GM-narrated. Garrik Ironside carries a seeded
Potion of Mind Reading; these tests probe an NPC bandit in an active
battle and prove the save mechanic plus the consume-on-use, and that a
bad action_key is rejected.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

SLUG = "potion-of-mind-reading"


async def _sheet(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    return (r.json() or {}).get("sheet") or {}


def _mind_reading_index(inventory):
    for i, it in enumerate(inventory):
        if isinstance(it, dict) and (it.get("_slug") or "") == SLUG:
            return i
    return -1


def _npc(cid, name="Bandit"):
    return {
        "id": cid, "char_id": None, "name": name,
        "initiative": 10, "hp_current": 200, "hp_max": 200, "ac": 12,
        "creature_type": "humanoid", "speed_walk": 30, "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


def _pc_tok(char):
    return {
        "id": f"tok_mr_{char['id']}",
        "char_id": char["id"], "name": char["name"],
        "initiative": 20, "hp_current": 85, "hp_max": 85,
        "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


@pytest_asyncio.fixture
async def battle_garrik(gm_client, roster):
    garrik = roster["Garrik Ironside"]
    garrik_sheet = await _sheet(gm_client, garrik["id"])
    inv = list(garrik_sheet.get("inventory") or [])
    a_cid = "tok_mr_a"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [_pc_tok(garrik), _npc(a_cid, "Bandit Alpha")],
              "turn_index": 0, "round": 1, "active": True},
    )
    try:
        yield garrik, inv, a_cid
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


async def test_mind_reading_probes_and_consumes(gm_client, gm_ws, battle_garrik):
    """Garrik probes a bandit's mind → a DC 13 WIS save is resolved, the
    potion is consumed, and a feature_used broadcast fires. (Like the Fire
    Breath harness test, the save outcome isn't asserted: bare NPC tokens
    without a stat block defer the save rather than auto-rolling it.)"""
    garrik, inv, a_cid = battle_garrik
    idx = _mind_reading_index(inv)
    assert idx >= 0, "Garrik must carry a Potion of Mind Reading"

    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/use_item_action",
        json={"inventory_index": idx, "action_key": "read",
              "target_combatant_ids": [a_cid]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["save_dc"] == 13
    assert data["save_ability"] == "WIS"
    assert data["consumed"] is True
    assert data["remaining_qty"] == 0

    results = data.get("results") or []
    assert len(results) == 1
    assert results[0].get("combatant_id") == a_cid
    assert "passed" in results[0], results[0]

    msgs = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == f"item-{SLUG}"
    ]
    assert msgs, "expected a feature_used broadcast for Mind Reading"


async def test_mind_reading_bad_action_key_404(gm_client, battle_garrik):
    """Error path: Mind Reading exposes only the `read` action — a
    `drink` action_key (the self-buff potions' key) is rejected 404."""
    garrik, inv, a_cid = battle_garrik
    idx = _mind_reading_index(inv)
    assert idx >= 0
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/use_item_action",
        json={"inventory_index": idx, "action_key": "drink",
              "target_combatant_ids": [a_cid]},
    )
    assert resp.status_code == 404, resp.text
