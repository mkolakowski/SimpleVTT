"""v2.193.0 — Potion of Fire Breath (RAW DMG p.187, uncommon): the first
OFFENSIVE consumable potion. Drinking exhales fire at the area — each
target makes a DC 13 DEX saving throw, 4d6 fire, half on a success — and
the potion is consumed.

The handler reuses the Necklace of Fireballs per-target save loop
(`_resolve_feature_save` → roll → `_apply_damage_to_combatant`) but
consumes the potion instead of decrementing a charge resource. Garrik
Ironside (Fighter) carries a seeded Potion of Fire Breath; these tests
exhale it at NPC bandits in an active battle and prove the save+damage
mechanic plus the consume-on-use, and that a bad action_key is rejected.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

SLUG = "potion-of-fire-breath"


async def _sheet(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    return (r.json() or {}).get("sheet") or {}


def _fire_breath_index(inventory):
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
        "id": f"tok_fb_{char['id']}",
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
    a_cid, b_cid = "tok_fb_a", "tok_fb_b"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [_pc_tok(garrik), _npc(a_cid, "Bandit Alpha"),
                             _npc(b_cid, "Bandit Beta")],
              "turn_index": 0, "round": 1, "active": True},
    )
    try:
        yield garrik, inv, a_cid, b_cid
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


async def test_fire_breath_exhales_and_consumes(gm_client, gm_ws, battle_garrik):
    """Garrik exhales fire at two bandits → a DC 13 DEX save is resolved
    per target (4d6 fire, half on a success), the potion is consumed, and
    a feature_used broadcast fires. (Like the Necklace/Javelin harness
    tests, damage isn't asserted: bare NPC tokens without a stat block
    defer the save rather than auto-rolling it server-side.)"""
    garrik, inv, a_cid, b_cid = battle_garrik
    idx = _fire_breath_index(inv)
    assert idx >= 0, "Garrik must carry a Potion of Fire Breath"

    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/use_item_action",
        json={"inventory_index": idx, "action_key": "breathe",
              "target_combatant_ids": [a_cid, b_cid]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["save_dc"] == 13
    assert data["save_ability"] == "DEX"
    assert data["dice"] == "4d6"
    assert data["consumed"] is True
    assert data["remaining_qty"] == 0

    results = data.get("results") or []
    assert len(results) == 2
    assert {a_cid, b_cid}.issubset({r.get("combatant_id") for r in results})
    for r in results:
        assert "damage_dealt" in r and "passed" in r, r

    msgs = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == f"item-{SLUG}"
    ]
    assert msgs, "expected a feature_used broadcast for Fire Breath"


async def test_fire_breath_bad_action_key_404(gm_client, battle_garrik):
    """Error path: Fire Breath exposes only the `breathe` action — a
    `drink` action_key (the self-buff potions' key) is rejected 404."""
    garrik, inv, a_cid, _b = battle_garrik
    idx = _fire_breath_index(inv)
    assert idx >= 0
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/use_item_action",
        json={"inventory_index": idx, "action_key": "drink",
              "target_combatant_ids": [a_cid]},
    )
    assert resp.status_code == 404, resp.text
