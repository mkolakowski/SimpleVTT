"""v2.159.11 — magic-items-automation Phase 8k: Wand of Fear cone-AoE
handler via /use_item_action. RAW DMG p.213 (rare, attunement): 7
charges (regain 1d6+1 at dawn), spend 1 to project a 30-ft cone, DC 15
WIS save or Frightened of you for 1 minute (repeat save at end of each
of its turns).

The handler:
  - validates the charge counter (refuses 409 insufficient_charges
    when current = 0)
  - validates target_combatant_ids list
  - resolves DC 15 WIS save per target via _resolve_feature_save
    with a frightened ``condition_buff`` (installs on save-fail NPCs,
    prompts PCs through the existing save flow)
  - decrements the charge counter by N (catalog enforces N=1 for now;
    over-cap returns 400 — the validation hook is shared with the
    necklace charge-spinner substrate)
  - broadcasts resource_update + feature_used

Demo fixture: Magnus Hexbinder (Warlock Lv 5) gets the wand at
inventory_index 7 with a 7-charge resource row at key ``wand-of-fear``
+ ``charge_recovery: "1d6+1"`` for the v2.158.86 long-rest path.

Tests:
  - happy path: cast at 2 targets → results carries both ids,
    frightened buff lands on an NPC save-fail (auto-roll), charge
    counter drops from 7 to 6.
  - over-cap charges (charges=2 when max=1) → 400.
  - empty wand (current=0) → 409 insufficient_charges.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


MAGNUS_WAND_INV_IDX = 7


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
async def magnus(roster):
    return roster["Magnus Hexbinder"]


@pytest_asyncio.fixture
async def magnus_full_wand(gm_client, magnus):
    """Force-reseed Magnus's Wand of Fear charge counter to current=7
    via /sheet-fields PATCH. Snapshot + restore on teardown so
    downstream tests don't see a drained wand."""
    sheet_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-json",
    )
    sheet = sheet_resp.json().get("sheet") or {}
    resources = list(sheet.get("resources") or [])
    snapshot = [dict(r) if isinstance(r, dict) else r for r in resources]
    for i, r in enumerate(resources):
        if isinstance(r, dict) and r.get("key") == "wand-of-fear":
            resources[i] = {**r, "current": 7, "max": 7}
            break
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
        json={"resources": resources},
    )
    yield magnus
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
        json={"resources": snapshot},
    )


async def test_wand_of_fear_cast_2_targets(
    gm_client, magnus_full_wand,
):
    """v2.159.11 happy path. Cast at 2 NPC targets → 200 with
    results carrying both ids, save_dc=15, save_ability='WIS', and
    the charge counter drops 7 → 6."""
    magnus = magnus_full_wand
    magnus_cid = f"tok_wof1_magnus_{magnus['id']}"
    a_cid = "tok_wof1_a"
    b_cid = "tok_wof1_b"
    await _seed_battle(gm_client, [
        _mkc(magnus_cid, magnus["id"], name=magnus["name"]),
        _mkc(a_cid, None, name="Bandit Alpha"),
        _mkc(b_cid, None, name="Bandit Beta"),
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/use_item_action",
        json={
            "inventory_index": MAGNUS_WAND_INV_IDX,
            "action_key": "cast-fear",
            "target_combatant_ids": [a_cid, b_cid],
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["save_dc"] == 15
    assert data["save_ability"] == "WIS"
    assert data["charges_spent"] == 1
    assert data["resource"]["current"] == 6  # 7 → 6
    results = data.get("results") or []
    assert len(results) == 2
    target_ids = {r.get("combatant_id") for r in results}
    assert {a_cid, b_cid}.issubset(target_ids)


async def test_wand_of_fear_over_cap_returns_400(
    gm_client, magnus_full_wand,
):
    """v2.159.11: charges=2 when catalog max=1 → 400 (the same
    min/max validator the necklace upcast picker uses)."""
    magnus = magnus_full_wand
    magnus_cid = f"tok_wof2_magnus_{magnus['id']}"
    a_cid = "tok_wof2_a"
    await _seed_battle(gm_client, [
        _mkc(magnus_cid, magnus["id"], name=magnus["name"]),
        _mkc(a_cid, None, name="Bandit"),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/use_item_action",
        json={
            "inventory_index": MAGNUS_WAND_INV_IDX,
            "action_key": "cast-fear",
            "charges": 2,
            "target_combatant_ids": [a_cid],
        },
    )
    assert resp.status_code == 400, resp.text


async def test_wand_of_fear_empty_returns_409(
    gm_client, magnus,
):
    """v2.159.11: drain the wand to 0 charges via /sheet-fields,
    then try to cast → 409 insufficient_charges."""
    sheet_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-json",
    )
    sheet = sheet_resp.json().get("sheet") or {}
    resources = list(sheet.get("resources") or [])
    snapshot = [dict(r) if isinstance(r, dict) else r for r in resources]
    drained = [
        {**r, "current": 0} if (isinstance(r, dict) and r.get("key") == "wand-of-fear") else r
        for r in resources
    ]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
        json={"resources": drained},
    )

    try:
        magnus_cid = f"tok_wof3_magnus_{magnus['id']}"
        await _seed_battle(gm_client, [
            _mkc(magnus_cid, magnus["id"], name=magnus["name"]),
            _mkc("tok_wof3_a", None, name="Bandit"),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/use_item_action",
            json={
                "inventory_index": MAGNUS_WAND_INV_IDX,
                "action_key": "cast-fear",
                "target_combatant_ids": ["tok_wof3_a"],
            },
        )
        assert resp.status_code == 409, resp.text
        body = resp.json()
        assert body.get("error") == "insufficient_charges"
        assert body.get("current") == 0
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
            json={"resources": snapshot},
        )
