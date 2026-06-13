"""v2.208.0 — magic-items-automation content tail: Eyes of Charming
through the same `/use_item_action` endpoint as the Staff of Charming,
via the generalized `_use_item_action_wand_of_fear` save-condition
handler. RAW DMG p.168 (uncommon, attunement): 3 charges (regain all at
dawn). Expend 1 (action) to cast charm person at one humanoid within 30
ft — fixed DC 13 WIS save or Charmed for 1 hour.

A near drop-in of the Staff of Charming entry: the only differences are
the fixed DC 13 (vs the staff's `"spell"` sentinel), the 3-charge pool,
and the feature label.

Demo home: Zara Emberfire (Draconic Sorcerer, Charlatan) — a CHA face
with no other attuned items, so the lenses are a clean 1/3 attunement.
The item index is looked up by `_slug`.

Tests:
  - happy: cast at 1 target → save_dc=13, save_ability='WIS',
    charges_spent=1, resource drops 3 → 2.
  - over-cap charges (charges=2 when max=1) → 400.
  - empty lenses (current=0) → 409 insufficient_charges.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


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
async def zara(roster):
    return roster["Zara Emberfire"]


@pytest_asyncio.fixture
async def zara_eyes(gm_client, zara):
    """Force-reseed Zara's Eyes of Charming charge counter to current=3
    via /sheet-fields PATCH. Snapshot + restore on teardown. Yields the
    inventory index resolved by `_slug`."""
    sheet = await _sheet(gm_client, zara["id"])
    resources = list(sheet.get("resources") or [])
    snapshot = [dict(r) if isinstance(r, dict) else r for r in resources]
    for i, r in enumerate(resources):
        if isinstance(r, dict) and r.get("key") == "eyes-of-charming":
            resources[i] = {**r, "current": 3, "max": 3}
            break
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/sheet-fields",
        json={"resources": resources},
    )
    idx = _slug_index(sheet.get("inventory") or [], "eyes-of-charming")
    assert idx >= 0, "Zara must carry seeded Eyes of Charming"
    yield {"char": zara, "idx": idx}
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/sheet-fields",
        json={"resources": snapshot},
    )


async def test_eyes_of_charming_cast_fixed_dc13(gm_client, zara_eyes):
    """v2.208.0 happy path. Cast charm person at 1 target → 200 with
    fixed save_dc=13, save_ability='WIS', and the charge counter drops
    3 → 2."""
    zara = zara_eyes["char"]
    idx = zara_eyes["idx"]
    zara_cid = f"tok_eoc1_zara_{zara['id']}"
    a_cid = "tok_eoc1_a"
    await _seed_battle(gm_client, [
        _mkc(zara_cid, zara["id"], name=zara["name"]),
        _mkc(a_cid, None, name="Bandit Alpha"),
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/use_item_action",
        json={
            "inventory_index": idx,
            "action_key": "cast-charm-person",
            "target_combatant_ids": [a_cid],
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["item_name"] == "Eyes of Charming"
    assert data["save_dc"] == 13
    assert data["save_ability"] == "WIS"
    assert data["charges_spent"] == 1
    assert data["resource"]["current"] == 2  # 3 → 2
    results = data.get("results") or []
    assert len(results) == 1
    assert results[0].get("combatant_id") == a_cid


async def test_eyes_of_charming_over_cap_returns_400(gm_client, zara_eyes):
    """v2.208.0: charges=2 when catalog max=1 → 400."""
    zara = zara_eyes["char"]
    idx = zara_eyes["idx"]
    zara_cid = f"tok_eoc2_zara_{zara['id']}"
    a_cid = "tok_eoc2_a"
    await _seed_battle(gm_client, [
        _mkc(zara_cid, zara["id"], name=zara["name"]),
        _mkc(a_cid, None, name="Bandit"),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/use_item_action",
        json={
            "inventory_index": idx,
            "action_key": "cast-charm-person",
            "charges": 2,
            "target_combatant_ids": [a_cid],
        },
    )
    assert resp.status_code == 400, resp.text


async def test_eyes_of_charming_empty_returns_409(gm_client, zara):
    """v2.208.0: drain the lenses to 0 charges via /sheet-fields, then
    try to cast → 409 insufficient_charges."""
    sheet = await _sheet(gm_client, zara["id"])
    resources = list(sheet.get("resources") or [])
    snapshot = [dict(r) if isinstance(r, dict) else r for r in resources]
    idx = _slug_index(sheet.get("inventory") or [], "eyes-of-charming")
    assert idx >= 0, "Zara must carry seeded Eyes of Charming"
    drained = [
        {**r, "current": 0}
        if (isinstance(r, dict) and r.get("key") == "eyes-of-charming")
        else r
        for r in resources
    ]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/sheet-fields",
        json={"resources": drained},
    )

    try:
        zara_cid = f"tok_eoc3_zara_{zara['id']}"
        await _seed_battle(gm_client, [
            _mkc(zara_cid, zara["id"], name=zara["name"]),
            _mkc("tok_eoc3_a", None, name="Bandit"),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/use_item_action",
            json={
                "inventory_index": idx,
                "action_key": "cast-charm-person",
                "target_combatant_ids": ["tok_eoc3_a"],
            },
        )
        assert resp.status_code == 409, resp.text
        body = resp.json()
        assert body.get("error") == "insufficient_charges"
        assert body.get("current") == 0
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/sheet-fields",
            json={"resources": snapshot},
        )
