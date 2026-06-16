"""v2.354.0 — magic-items: Robe of Scintillating Colors (RAW DMG p.194,
very rare, attunement) through the `/use_item_action` endpoint + the
generalized `_use_item_action_wand_of_fear` save-condition handler. Fifth
Bucket-A charge-cast item off the v2.344.5 triage — the radius `stunned`
shape, 3 charges, DC 15 WIS. An action displays dazzling colors → each
creature within 30 ft that can see the wearer makes a DC 15 WIS save or
is stunned until the end of the wearer's next turn. The companion
"attackers have disadvantage" self-buff is GM-narrated.

Demo home: Lyra Sunstrider (Bard), seeded equipped+attuned with a
`robe-of-scintillating-colors` 3-charge resource. The item index +
resource row are looked up by `_slug` / key.

Tests:
  - happy: dazzling-display at 2 targets → save_dc=15, save_ability='WIS',
    charges_spent=1, resource 3 → 2, both ids in results.
  - empty robe (current=0) → 409 insufficient_charges.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_SLUG = "robe-of-scintillating-colors"


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
async def lyra_full_robe(gm_client, lyra):
    """Force-reseed Lyra's Robe of Scintillating Colors charge counter to
    current=3 via /sheet-fields PATCH. Snapshot + restore on teardown.
    Yields the inventory index resolved by `_slug`."""
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
    assert idx >= 0, "Lyra must carry a seeded Robe of Scintillating Colors"
    yield {"char": lyra, "idx": idx}
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/sheet-fields",
        json={"resources": snapshot},
    )


async def test_robe_dazzling_display_2_targets(gm_client, lyra_full_robe):
    """v2.354.0 happy path. Dazzling display at 2 NPC targets → 200 with
    results carrying both ids, save_dc=15, save_ability='WIS', and the
    charge counter drops 3 → 2."""
    lyra = lyra_full_robe["char"]
    idx = lyra_full_robe["idx"]
    lyra_cid = f"tok_rsc1_lyra_{lyra['id']}"
    a_cid = "tok_rsc1_a"
    b_cid = "tok_rsc1_b"
    await _seed_battle(gm_client, [
        _mkc(lyra_cid, lyra["id"], name=lyra["name"]),
        _mkc(a_cid, None, name="Bandit Alpha"),
        _mkc(b_cid, None, name="Bandit Beta"),
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/use_item_action",
        json={
            "inventory_index": idx,
            "action_key": "dazzling-display",
            "target_combatant_ids": [a_cid, b_cid],
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["item_name"] == "Robe of Scintillating Colors"
    assert data["save_dc"] == 15
    assert data["save_ability"] == "WIS"
    assert data["charges_spent"] == 1
    assert data["resource"]["current"] == 2  # 3 → 2
    results = data.get("results") or []
    assert len(results) == 2
    target_ids = {r.get("combatant_id") for r in results}
    assert {a_cid, b_cid}.issubset(target_ids)


async def test_robe_empty_returns_409(gm_client, lyra):
    """v2.354.0: drain the robe to 0 charges via /sheet-fields, then try to
    invoke → 409 insufficient_charges."""
    sheet = await _sheet(gm_client, lyra["id"])
    resources = list(sheet.get("resources") or [])
    snapshot = [dict(r) if isinstance(r, dict) else r for r in resources]
    idx = _slug_index(sheet.get("inventory") or [], _SLUG)
    assert idx >= 0, "Lyra must carry a seeded Robe of Scintillating Colors"
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
        lyra_cid = f"tok_rsc2_lyra_{lyra['id']}"
        await _seed_battle(gm_client, [
            _mkc(lyra_cid, lyra["id"], name=lyra["name"]),
            _mkc("tok_rsc2_a", None, name="Bandit"),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/use_item_action",
            json={
                "inventory_index": idx,
                "action_key": "dazzling-display",
                "target_combatant_ids": ["tok_rsc2_a"],
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
