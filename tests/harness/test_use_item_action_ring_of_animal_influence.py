"""v2.353.0 — magic-items: Ring of Animal Influence (RAW DMG p.190, rare,
NO attunement) through the `/use_item_action` endpoint + the generalized
`_use_item_action_wand_of_fear` save-condition handler. Fourth Bucket-A
charge-cast item off the v2.344.5 triage — the single-target `charmed`
shape (Animal Friendship), 3 charges, DC 13 WIS. An action casts animal
friendship on one beast → charmed. The other two charge-spells (fear on
beasts, speak with animals) are GM-narrated.

Demo home: Mira Greenleaf (Circle of the Moon Druid), seeded equipped
(no attunement) with a `ring-of-animal-influence` 3-charge resource. The
item index + resource row are looked up by `_slug` / key.

Tests:
  - happy: cast-animal-friendship at 1 target → save_dc=13, save_ability=
    'WIS', charges_spent=1, resource 3 → 2, the id in results.
  - empty ring (current=0) → 409 insufficient_charges.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_SLUG = "ring-of-animal-influence"


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
        "creature_type": "beast",
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
async def mira(roster):
    return roster["Mira Greenleaf"]


@pytest_asyncio.fixture
async def mira_full_ring(gm_client, mira):
    """Force-reseed Mira's Ring of Animal Influence charge counter to
    current=3 via /sheet-fields PATCH. Snapshot + restore on teardown.
    Yields the inventory index resolved by `_slug`."""
    sheet = await _sheet(gm_client, mira["id"])
    resources = list(sheet.get("resources") or [])
    snapshot = [dict(r) if isinstance(r, dict) else r for r in resources]
    for i, r in enumerate(resources):
        if isinstance(r, dict) and r.get("key") == _SLUG:
            resources[i] = {**r, "current": 3, "max": 3}
            break
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/sheet-fields",
        json={"resources": resources},
    )
    idx = _slug_index(sheet.get("inventory") or [], _SLUG)
    assert idx >= 0, "Mira must carry a seeded Ring of Animal Influence"
    yield {"char": mira, "idx": idx}
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/sheet-fields",
        json={"resources": snapshot},
    )


async def test_ring_animal_friendship_one_target(gm_client, mira_full_ring):
    """v2.353.0 happy path. Animal friendship at 1 NPC beast target → 200
    with the id in results, save_dc=13, save_ability='WIS', and the charge
    counter drops 3 → 2."""
    mira = mira_full_ring["char"]
    idx = mira_full_ring["idx"]
    mira_cid = f"tok_rai1_mira_{mira['id']}"
    beast_cid = "tok_rai1_beast"
    await _seed_battle(gm_client, [
        _mkc(mira_cid, mira["id"], name=mira["name"]),
        _mkc(beast_cid, None, name="Wolf"),
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/use_item_action",
        json={
            "inventory_index": idx,
            "action_key": "cast-animal-friendship",
            "target_combatant_ids": [beast_cid],
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["item_name"] == "Ring of Animal Influence"
    assert data["save_dc"] == 13
    assert data["save_ability"] == "WIS"
    assert data["charges_spent"] == 1
    assert data["resource"]["current"] == 2  # 3 → 2
    results = data.get("results") or []
    assert len(results) == 1
    assert results[0].get("combatant_id") == beast_cid


async def test_ring_animal_influence_empty_returns_409(gm_client, mira):
    """v2.353.0: drain the ring to 0 charges via /sheet-fields, then try to
    invoke → 409 insufficient_charges."""
    sheet = await _sheet(gm_client, mira["id"])
    resources = list(sheet.get("resources") or [])
    snapshot = [dict(r) if isinstance(r, dict) else r for r in resources]
    idx = _slug_index(sheet.get("inventory") or [], _SLUG)
    assert idx >= 0, "Mira must carry a seeded Ring of Animal Influence"
    drained = [
        {**r, "current": 0}
        if (isinstance(r, dict) and r.get("key") == _SLUG)
        else r
        for r in resources
    ]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/sheet-fields",
        json={"resources": drained},
    )
    try:
        mira_cid = f"tok_rai2_mira_{mira['id']}"
        await _seed_battle(gm_client, [
            _mkc(mira_cid, mira["id"], name=mira["name"]),
            _mkc("tok_rai2_beast", None, name="Wolf"),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/use_item_action",
            json={
                "inventory_index": idx,
                "action_key": "cast-animal-friendship",
                "target_combatant_ids": ["tok_rai2_beast"],
            },
        )
        assert resp.status_code == 409, resp.text
        body = resp.json()
        assert body.get("error") == "insufficient_charges"
        assert body.get("current") == 0
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/sheet-fields",
            json={"resources": snapshot},
        )
