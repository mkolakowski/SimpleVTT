"""v2.159.9 — magic-items-automation Phase 8i: Necklace of Fireballs
sphere-AoE handler via /use_item_action. RAW DMG p.183: each bead is
a 3rd-level Fireball (8d6 fire, DC 15 DEX save half, 20-ft sphere).
The handler:
  - validates the charge counter (refuses 409 insufficient_charges
    when bead count = 0)
  - validates target_combatant_ids list
  - resolves DC 15 DEX save per target via _resolve_feature_save
  - applies 8d6 fire (half on pass) via _apply_damage_to_combatant
  - decrements the charge counter by 1
  - broadcasts resource_update + feature_used

v1 ships single-bead throws — multi-bead upcast is Phase 8j.

Demo fixture: Thalindra Moonwhisper (Wizard Lv 7) gets the necklace
at inventory_index 11 with a 6-bead resource row at key
``necklace-of-fireballs``. RAW says "the necklace doesn't regenerate"
so the resource row has ``reset: "none"``.

Tests:
  - happy path: throw bead at 2 targets → results + charge=5
  - empty necklace → 409 insufficient_charges
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


THAL_NECKLACE_INV_IDX = 11


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


@pytest_asyncio.fixture
async def thalindra(roster):
    return roster["Thalindra Moonwhisper"]


@pytest_asyncio.fixture
async def thalindra_full_necklace(gm_client, thalindra):
    """Force-reseed Thalindra's necklace to a full 6 beads by
    PATCHing the inventory + resource row directly. We don't have a
    /rest-style refill for this resource (reset='none' RAW), so
    teardown explicitly puts it back."""
    sheet_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-json",
    )
    sheet = sheet_resp.json().get("sheet") or {}
    resources = list(sheet.get("resources") or [])
    # Snapshot for teardown.
    snapshot = [dict(r) if isinstance(r, dict) else r for r in resources]

    # Force the necklace resource row to current=6.
    for i, r in enumerate(resources):
        if isinstance(r, dict) and r.get("key") == "necklace-of-fireballs":
            resources[i] = {**r, "current": 6, "max": 6}
            break
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-fields",
        json={"resources": resources},
    )
    yield thalindra
    # Teardown: restore the snapshot so prior tests' assertions
    # downstream see the original state.
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-fields",
        json={"resources": snapshot},
    )


async def test_necklace_throw_bead_2_targets(
    gm_client, thalindra_full_necklace,
):
    """v2.159.9 happy path. Throw one bead at 2 targets → results
    carries both ids, save-resolved per target, charge counter drops
    from 6 to 5."""
    thalindra = thalindra_full_necklace
    thal_cid = f"tok_nef1_thal_{thalindra['id']}"
    a_cid = "tok_nef1_a"
    b_cid = "tok_nef1_b"
    await _seed_battle(gm_client, [
        _mkc(thal_cid, thalindra["id"], name=thalindra["name"]),
        _mkc(a_cid, None, name="Bandit Alpha"),
        _mkc(b_cid, None, name="Bandit Beta"),
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/use_item_action",
        json={
            "inventory_index": THAL_NECKLACE_INV_IDX,
            "action_key": "throw-bead",
            "target_combatant_ids": [a_cid, b_cid],
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["save_dc"] == 15
    assert data["save_ability"] == "DEX"
    assert data["resource"]["current"] == 5  # 6 → 5
    results = data.get("results") or []
    assert len(results) == 2
    target_ids = {r.get("combatant_id") for r in results}
    assert {a_cid, b_cid}.issubset(target_ids)


async def test_necklace_empty_returns_409(
    gm_client, thalindra,
):
    """v2.159.9: drain the necklace to 0 beads via /sheet-fields,
    then try to throw → 409 insufficient_charges."""
    # Snapshot resources for teardown.
    sheet_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-json",
    )
    sheet = sheet_resp.json().get("sheet") or {}
    resources = list(sheet.get("resources") or [])
    snapshot = [dict(r) if isinstance(r, dict) else r for r in resources]
    # Force the necklace row to current=0.
    drained = [
        {**r, "current": 0} if (isinstance(r, dict) and r.get("key") == "necklace-of-fireballs") else r
        for r in resources
    ]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-fields",
        json={"resources": drained},
    )

    try:
        thal_cid = f"tok_nef2_thal_{thalindra['id']}"
        await _seed_battle(gm_client, [
            _mkc(thal_cid, thalindra["id"], name=thalindra["name"]),
            _mkc("tok_nef2_a", None, name="Bandit"),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/use_item_action",
            json={
                "inventory_index": THAL_NECKLACE_INV_IDX,
                "action_key": "throw-bead",
                "target_combatant_ids": ["tok_nef2_a"],
            },
        )
        assert resp.status_code == 409, resp.text
        body = resp.json()
        assert body.get("error") == "insufficient_charges"
        assert body.get("current") == 0
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-fields",
            json={"resources": snapshot},
        )
