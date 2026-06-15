"""v2.350.0 — magic-items: Pipes of Haunting (RAW DMG p.184, uncommon,
NO attunement) through the `/use_item_action` endpoint + the generalized
`_use_item_action_wand_of_fear` save-condition handler. First Bucket-A
charge-cast item off the v2.344.5 stub triage — a near-verbatim Mace of
Terror clone (30-ft radius WIS → frightened, 3 charges) but without
attunement (RAW needs wind-instrument proficiency, GM-narrated). Expend
1 of 3 charges → each chosen creature within 30 ft makes a DC 15 WIS
save or is frightened of the wielder for 1 minute.

Demo home: Lyra Sunstrider (Bard). Seeded equipped (no attunement) with
a `pipes-of-haunting` charge resource. The item index + resource row are
looked up by `_slug` / key.

Tests:
  - happy: haunting tune at 2 targets → save_dc=15, save_ability='WIS',
    charges_spent=1, resource 3 → 2, both ids in results.
  - empty pipes (current=0) → 409 insufficient_charges.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_SLUG = "pipes-of-haunting"


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
async def lyra(roster):
    return roster["Lyra Sunstrider"]


@pytest_asyncio.fixture
async def lyra_full_pipes(gm_client, lyra):
    """Force-reseed Lyra's Pipes of Haunting charge counter to current=3
    via /sheet-fields PATCH. Snapshot + restore on teardown. Yields the
    inventory index resolved by `_slug`."""
    sheet = await _sheet(gm_client, lyra["id"])
    resources = list(sheet.get("resources") or [])
    snapshot = [dict(r) if isinstance(r, dict) else r for r in resources]
    for i, r in enumerate(resources):
        if isinstance(r, dict) and r.get("key") == _SLUG:
            resources[i] = {**r, "current": 3, "max": 3}
            break
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/sheet-fields",
        json={"resources": resources},
    )
    idx = _slug_index(sheet.get("inventory") or [], _SLUG)
    assert idx >= 0, "Lyra must carry a seeded Pipes of Haunting"
    yield {"char": lyra, "idx": idx}
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/sheet-fields",
        json={"resources": snapshot},
    )


async def test_pipes_of_haunting_tune_2_targets(gm_client, lyra_full_pipes):
    """v2.350.0 happy path. Haunting tune at 2 NPC targets → 200 with
    results carrying both ids, save_dc=15, save_ability='WIS', and the
    charge counter drops 3 → 2."""
    lyra = lyra_full_pipes["char"]
    idx = lyra_full_pipes["idx"]
    lyra_cid = f"tok_poh1_lyra_{lyra['id']}"
    a_cid = "tok_poh1_a"
    b_cid = "tok_poh1_b"
    await _seed_battle(gm_client, [
        _mkc(lyra_cid, lyra["id"], name=lyra["name"]),
        _mkc(a_cid, None, name="Bandit Alpha"),
        _mkc(b_cid, None, name="Bandit Beta"),
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/use_item_action",
        json={
            "inventory_index": idx,
            "action_key": "play-haunting-tune",
            "target_combatant_ids": [a_cid, b_cid],
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["item_name"] == "Pipes of Haunting"
    assert data["save_dc"] == 15
    assert data["save_ability"] == "WIS"
    assert data["charges_spent"] == 1
    assert data["resource"]["current"] == 2  # 3 → 2
    results = data.get("results") or []
    assert len(results) == 2
    target_ids = {r.get("combatant_id") for r in results}
    assert {a_cid, b_cid}.issubset(target_ids)


async def test_pipes_of_haunting_empty_returns_409(gm_client, lyra):
    """v2.350.0: drain the pipes to 0 charges via /sheet-fields, then try
    to invoke → 409 insufficient_charges."""
    sheet = await _sheet(gm_client, lyra["id"])
    resources = list(sheet.get("resources") or [])
    snapshot = [dict(r) if isinstance(r, dict) else r for r in resources]
    idx = _slug_index(sheet.get("inventory") or [], _SLUG)
    assert idx >= 0, "Lyra must carry a seeded Pipes of Haunting"
    drained = [
        {**r, "current": 0}
        if (isinstance(r, dict) and r.get("key") == _SLUG)
        else r
        for r in resources
    ]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/sheet-fields",
        json={"resources": drained},
    )
    try:
        lyra_cid = f"tok_poh2_lyra_{lyra['id']}"
        await _seed_battle(gm_client, [
            _mkc(lyra_cid, lyra["id"], name=lyra["name"]),
            _mkc("tok_poh2_a", None, name="Bandit"),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/use_item_action",
            json={
                "inventory_index": idx,
                "action_key": "play-haunting-tune",
                "target_combatant_ids": ["tok_poh2_a"],
            },
        )
        assert resp.status_code == 409, resp.text
        body = resp.json()
        assert body.get("error") == "insufficient_charges"
        assert body.get("current") == 0
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/sheet-fields",
            json={"resources": snapshot},
        )
