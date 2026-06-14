"""v2.271.0 — charged-items Phase 3 (closes the phase): Horn of Blasting
(RAW DMG p.174, uncommon, NO attunement). A save-for-half AoE-damage
charge action with NO resource row — the horn has no charges (it's
at-will; the RAW 20% self-destruct per blow is GM-narrated). The
``blast`` action routes through the new ``_use_item_action_horn_of_
blasting`` handler: each creature in a 30-ft cone makes a DC 15 CON save
→ 5d6 thunder + deafened 1 minute on a fail, half damage + no deafen on
a pass (the deafen condition installs only on a failed save).

Demo fixture: Krieger Stonefist (Half-Orc Barbarian) carries an equipped
Horn of Blasting (no attunement, no resource row).

Tests:
  - happy path: blast at 2 targets in an active battle → action_kind
    "attack_aoe", save_dc 15 CON, dice "5d6", damage_type "thunder",
    condition_key "deafened", both ids resolved with per-target
    passed/damage_dealt/deafened fields; no resource field
  - too many targets (>24) → 400
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_SLUG = "horn-of-blasting"


def _mkc(cid, char_id=None, name="X", hp_max=200, ac=1):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": hp_max, "hp_max": hp_max,
        "ac": ac,
        "buffs": [],
        "creature_type": "humanoid",
        "speed_walk": 30,
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _seed_battle(gm_client, combatants):
    return await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


async def _horn_inv_idx(gm_client, char_id):
    sheet_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    sheet = sheet_resp.json().get("sheet") or {}
    inv = sheet.get("inventory") or []
    for i, it in enumerate(inv):
        if isinstance(it, dict) and it.get("_slug") == _SLUG:
            return i
    raise AssertionError("Krieger has no horn-of-blasting inventory item")


@pytest_asyncio.fixture
async def krieger(roster):
    return roster["Krieger Stonefist"]


async def test_horn_of_blasting_blast_2_targets(gm_client, krieger):
    """Happy path: blast at 2 targets in an active battle → action_kind
    "attack_aoe", save_dc 15 CON, dice "5d6", damage_type "thunder",
    condition_key "deafened", both ids resolved with per-target fields
    and no resource (the horn is charge-less)."""
    idx = await _horn_inv_idx(gm_client, krieger["id"])
    k_cid = f"tok_hob1_krieger_{krieger['id']}"
    a_cid = "tok_hob1_a"
    b_cid = "tok_hob1_b"
    await _seed_battle(gm_client, [
        _mkc(k_cid, krieger["id"], name=krieger["name"]),
        _mkc(a_cid, None, name="Bandit Alpha"),
        _mkc(b_cid, None, name="Bandit Beta"),
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/use_item_action",
        json={
            "inventory_index": idx,
            "action_key": "blast",
            "target_combatant_ids": [a_cid, b_cid],
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["action_kind"] == "attack_aoe"
    assert data["save_dc"] == 15
    assert data["save_ability"] == "CON"
    assert data["dice"] == "5d6"
    assert data["damage_type"] == "thunder"
    assert data["condition_key"] == "deafened"
    assert "resource" not in data  # the horn has no charges/resource row
    results = data.get("results") or []
    assert len(results) == 2
    target_ids = {r.get("combatant_id") for r in results}
    assert {a_cid, b_cid}.issubset(target_ids)
    for r in results:
        assert isinstance(r.get("damage_dealt"), int)
        assert isinstance(r.get("deafened"), bool)
        # RAW: deafened iff the save failed.
        assert r["deafened"] == (r.get("passed") is False)


async def test_horn_of_blasting_too_many_targets_returns_400(gm_client, krieger):
    """The cone caps at 24 targets — a list of 25 → 400."""
    idx = await _horn_inv_idx(gm_client, krieger["id"])
    k_cid = f"tok_hob2_krieger_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(k_cid, krieger["id"], name=krieger["name"]),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/use_item_action",
        json={
            "inventory_index": idx,
            "action_key": "blast",
            "target_combatant_ids": [f"tok_hob2_t{i}" for i in range(25)],
        },
    )
    assert resp.status_code == 400, resp.text
