"""v2.351.0 — magic-items: Rod of Rulership (RAW DMG p.197, rare,
attunement) through the `/use_item_action` endpoint + the generalized
`_use_item_action_wand_of_fear` save-condition handler. Second Bucket-A
charge-cast item off the v2.344.5 triage — the Staff of Charming
`charmed` condition on the Mace of Terror radius-target shape, with a
single 1/dawn use (the resource refills on a long rest). An action
commands obedience from each chosen creature within 120 ft → DC 15 WIS
save or charmed (regards the wielder as its trusted leader) for 1 minute.

Demo home: Dame Seraphine Vael (Vengeance Paladin), seeded equipped +
attuned with a `rod-of-rulership` 1/dawn resource (the `/use_item_action`
path gates on `attuned` for attunement items). The item index + resource
row are looked up by `_slug` / key.

Tests:
  - happy: command-obedience at 2 targets → save_dc=15, save_ability='WIS',
    charges_spent=1, resource 1 → 0, both ids in results.
  - empty rod (current=0) → 409 insufficient_charges.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_SLUG = "rod-of-rulership"


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
async def seraphine(roster):
    return roster["Dame Seraphine Vael"]


@pytest_asyncio.fixture
async def seraphine_full_rod(gm_client, seraphine):
    """Force-reseed Seraphine's Rod of Rulership use counter to current=1
    via /sheet-fields PATCH. Snapshot + restore on teardown. Yields the
    inventory index resolved by `_slug`."""
    sheet = await _sheet(gm_client, seraphine["id"])
    resources = list(sheet.get("resources") or [])
    snapshot = [dict(r) if isinstance(r, dict) else r for r in resources]
    for i, r in enumerate(resources):
        if isinstance(r, dict) and r.get("key") == _SLUG:
            resources[i] = {**r, "current": 1, "max": 1}
            break
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{seraphine['id']}/sheet-fields",
        json={"resources": resources},
    )
    idx = _slug_index(sheet.get("inventory") or [], _SLUG)
    assert idx >= 0, "Seraphine must carry a seeded Rod of Rulership"
    yield {"char": seraphine, "idx": idx}
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{seraphine['id']}/sheet-fields",
        json={"resources": snapshot},
    )


async def test_rod_of_rulership_command_2_targets(gm_client, seraphine_full_rod):
    """v2.351.0 happy path. Command Obedience at 2 NPC targets → 200 with
    results carrying both ids, save_dc=15, save_ability='WIS', and the use
    counter drops 1 → 0."""
    seraphine = seraphine_full_rod["char"]
    idx = seraphine_full_rod["idx"]
    sera_cid = f"tok_ror1_sera_{seraphine['id']}"
    a_cid = "tok_ror1_a"
    b_cid = "tok_ror1_b"
    await _seed_battle(gm_client, [
        _mkc(sera_cid, seraphine["id"], name=seraphine["name"]),
        _mkc(a_cid, None, name="Bandit Alpha"),
        _mkc(b_cid, None, name="Bandit Beta"),
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{seraphine['id']}/use_item_action",
        json={
            "inventory_index": idx,
            "action_key": "command-obedience",
            "target_combatant_ids": [a_cid, b_cid],
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["item_name"] == "Rod of Rulership"
    assert data["save_dc"] == 15
    assert data["save_ability"] == "WIS"
    assert data["charges_spent"] == 1
    assert data["resource"]["current"] == 0  # 1 → 0
    results = data.get("results") or []
    assert len(results) == 2
    target_ids = {r.get("combatant_id") for r in results}
    assert {a_cid, b_cid}.issubset(target_ids)


async def test_rod_of_rulership_empty_returns_409(gm_client, seraphine):
    """v2.351.0: drain the rod to 0 uses via /sheet-fields, then try to
    invoke → 409 insufficient_charges."""
    sheet = await _sheet(gm_client, seraphine["id"])
    resources = list(sheet.get("resources") or [])
    snapshot = [dict(r) if isinstance(r, dict) else r for r in resources]
    idx = _slug_index(sheet.get("inventory") or [], _SLUG)
    assert idx >= 0, "Seraphine must carry a seeded Rod of Rulership"
    drained = [
        {**r, "current": 0}
        if (isinstance(r, dict) and r.get("key") == _SLUG)
        else r
        for r in resources
    ]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{seraphine['id']}/sheet-fields",
        json={"resources": drained},
    )
    try:
        sera_cid = f"tok_ror2_sera_{seraphine['id']}"
        await _seed_battle(gm_client, [
            _mkc(sera_cid, seraphine["id"], name=seraphine["name"]),
            _mkc("tok_ror2_a", None, name="Bandit"),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{seraphine['id']}/use_item_action",
            json={
                "inventory_index": idx,
                "action_key": "command-obedience",
                "target_combatant_ids": ["tok_ror2_a"],
            },
        )
        assert resp.status_code == 409, resp.text
        body = resp.json()
        assert body.get("error") == "insufficient_charges"
        assert body.get("current") == 0
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{seraphine['id']}/sheet-fields",
            json={"resources": snapshot},
        )
