"""v2.355.0 — magic-items: Rope of Entanglement (RAW DMG p.198, rare,
NO attunement) through the `/use_item_action` endpoint + the generalized
`_use_item_action_wand_of_fear` save-condition handler. Sixth Bucket-A
item off the v2.344.5 triage, and the **first `unlimited` (no-charge)**
item: a command-word action entangles one creature within 20 ft → DC 15
DEX save or restrained until released. RAW has no daily charges (the
only limit is the rope's own AC 20 / 20 HP, GM-narrated), so the catalog
flags it `unlimited: True` and the handler skips the resource lookup +
decrement.

Demo home: Kael Brightleaf (Monk), seeded equipped (no attunement, NO
charge resource). The item index is looked up by `_slug`.

Tests:
  - happy: entangle at 1 target → save_dc=15, save_ability='DEX',
    charges_spent=0, resource is None, the id in results.
  - repeatable: a SECOND invocation also succeeds (no charge depletion) —
    proving the unlimited path doesn't gate on a resource pool.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_SLUG = "rope-of-entanglement"


def _slug_index(inventory, slug):
    for i, it in enumerate(inventory):
        if isinstance(it, dict) and (it.get("_slug") or "") == slug:
            return i
    return -1


def _mkc(cid, char_id=None, name="X", hp_max=200):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": hp_max, "hp_max": hp_max,
        "ac": 1,
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


async def _sheet(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    return (r.json() or {}).get("sheet") or {}


@pytest_asyncio.fixture
async def kael(roster):
    return roster["Kael Brightleaf"]


async def _rope_idx(gm_client, kael):
    sheet = await _sheet(gm_client, kael["id"])
    idx = _slug_index(sheet.get("inventory") or [], _SLUG)
    assert idx >= 0, "Kael must carry a seeded Rope of Entanglement"
    return idx


async def _entangle(gm_client, kael, idx, target_id):
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{kael['id']}/use_item_action",
        json={
            "inventory_index": idx,
            "action_key": "entangle",
            "target_combatant_ids": [target_id],
        },
    )


async def test_rope_entangle_one_target(gm_client, kael):
    """v2.355.0 happy path. Entangle at 1 NPC target → 200 with the id in
    results, save_dc=15, save_ability='DEX'. As an unlimited item it
    reports charges_spent=0 and resource=None (no charge pool)."""
    idx = await _rope_idx(gm_client, kael)
    kael_cid = f"tok_roe1_kael_{kael['id']}"
    tgt_cid = "tok_roe1_target"
    await _seed_battle(gm_client, [
        _mkc(kael_cid, kael["id"], name=kael["name"]),
        _mkc(tgt_cid, None, name="Bandit"),
    ])
    resp = await _entangle(gm_client, kael, idx, tgt_cid)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["item_name"] == "Rope of Entanglement"
    assert data["save_dc"] == 15
    assert data["save_ability"] == "DEX"
    assert data["charges_spent"] == 0
    assert data["resource"] is None
    results = data.get("results") or []
    assert len(results) == 1
    assert results[0].get("combatant_id") == tgt_cid


async def test_rope_is_unlimited(gm_client, kael):
    """v2.355.0: a SECOND entangle also succeeds — the unlimited path never
    depletes (no `insufficient_charges` 409), unlike the charge-pool
    items."""
    idx = await _rope_idx(gm_client, kael)
    kael_cid = f"tok_roe2_kael_{kael['id']}"
    tgt_cid = "tok_roe2_target"
    await _seed_battle(gm_client, [
        _mkc(kael_cid, kael["id"], name=kael["name"]),
        _mkc(tgt_cid, None, name="Bandit"),
    ])
    first = await _entangle(gm_client, kael, idx, tgt_cid)
    assert first.status_code == 200, first.text
    second = await _entangle(gm_client, kael, idx, tgt_cid)
    assert second.status_code == 200, second.text
    assert second.json().get("resource") is None
