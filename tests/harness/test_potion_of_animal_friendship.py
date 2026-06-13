"""v2.202.0 — Potion of Animal Friendship (RAW DMG p.187, uncommon): the
second single-target save consumable. Drinking lets you charm one beast —
the target makes a DC 13 WIS saving throw; on a failure it's charmed — and
the potion is consumed.

The handler routes through the generalised Mind-Reading WIS-save loop
(`_resolve_feature_save`) with no damage roll — no HP changes; the charm
itself and the beast-only restriction are GM-narrated. Garrik Ironside
carries a seeded Potion of Animal Friendship; these tests charm an NPC in
an active battle and prove the save mechanic plus consume-on-use, and that
a bad action_key is rejected.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

SLUG = "potion-of-animal-friendship"


async def _sheet(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    return (r.json() or {}).get("sheet") or {}


def _slug_index(inventory):
    for i, it in enumerate(inventory):
        if isinstance(it, dict) and (it.get("_slug") or "") == SLUG:
            return i
    return -1


def _npc(cid, name="Wolf"):
    return {
        "id": cid, "char_id": None, "name": name,
        "initiative": 10, "hp_current": 200, "hp_max": 200, "ac": 12,
        "creature_type": "beast", "speed_walk": 40, "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


def _pc_tok(char):
    return {
        "id": f"tok_af_{char['id']}",
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
    a_cid = "tok_af_a"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [_pc_tok(garrik), _npc(a_cid, "Dire Wolf")],
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


async def test_animal_friendship_charms_and_consumes(
    gm_client, gm_ws, battle_garrik,
):
    """Garrik charms a wolf → a DC 13 WIS save is resolved, the potion is
    consumed, and a feature_used broadcast fires. (Bare NPC tokens without
    a stat block defer the save rather than auto-rolling it.)"""
    garrik, inv, a_cid = battle_garrik
    idx = _slug_index(inv)
    assert idx >= 0, "Garrik must carry a Potion of Animal Friendship"

    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/use_item_action",
        json={"inventory_index": idx, "action_key": "charm",
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
    assert msgs, "expected a feature_used broadcast for Animal Friendship"


async def test_animal_friendship_bad_action_key_404(gm_client, battle_garrik):
    """Error path: Animal Friendship exposes only the `charm` action — a
    `drink` action_key (the self-buff potions' key) is rejected 404."""
    garrik, inv, a_cid = battle_garrik
    idx = _slug_index(inv)
    assert idx >= 0
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/use_item_action",
        json={"inventory_index": idx, "action_key": "drink",
              "target_combatant_ids": [a_cid]},
    )
    assert resp.status_code == 404, resp.text
