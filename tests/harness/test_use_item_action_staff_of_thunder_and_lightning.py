"""v2.272.0 — charged-items Phase 2: Staff of Thunder and Lightning (RAW
DMG p.202, very rare, attunement): 5 charges (regain 1d6+1 at dawn). v1
ships the marquee Thunder action through the generalized save-for-half
AoE-damage handler (the same path as the Staff of Fire / Frost / Swarming
Insects / Necklace of Fireballs):

  - a flat DC 17 CON save (Thunder is RAW DC 17, not "your spell save DC"),
  - the dice / damage type / charge cost / feature label all come from the
    catalog action_def (2d6 thunder, CON save),
  - when ``charges`` is omitted the spend defaults to the action's
    ``min_charges`` (Thunder is a fixed 2-charge spend, no upcast).

Demo fixture: Magnus Hexbinder (Bronze Dragonborn Warlock) carries an
equipped + attuned Staff of Thunder and Lightning + a 5-charge resource
row at key ``staff-of-thunder-and-lightning``.

Tests:
  - happy path: Thunder at 2 targets (no charges param) → save_dc=17 CON,
    dice=2d6, charges_spent=2, resource 5 → 3, both ids resolved
  - under min charges (1 < 2) → 400
  - empty staff (drained below 2) → 409 insufficient_charges
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_SLUG = "staff-of-thunder-and-lightning"


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


async def _staff_inv_idx(gm_client, char_id):
    sheet_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    sheet = sheet_resp.json().get("sheet") or {}
    inv = sheet.get("inventory") or []
    for i, it in enumerate(inv):
        if isinstance(it, dict) and it.get("_slug") == _SLUG:
            return i
    raise AssertionError("Magnus has no staff-of-thunder-and-lightning item")


@pytest_asyncio.fixture
async def magnus(roster):
    return roster["Magnus Hexbinder"]


@pytest_asyncio.fixture
async def magnus_full_staff(gm_client, magnus):
    """Force-reseed Magnus's Staff of Thunder and Lightning to a full 5
    charges, restoring the snapshot on teardown."""
    sheet_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-json",
    )
    sheet = sheet_resp.json().get("sheet") or {}
    resources = list(sheet.get("resources") or [])
    snapshot = [dict(r) if isinstance(r, dict) else r for r in resources]
    for i, r in enumerate(resources):
        if isinstance(r, dict) and r.get("key") == _SLUG:
            resources[i] = {**r, "current": 5, "max": 5}
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


async def test_staff_of_thunder_and_lightning_thunder_2_targets(gm_client, magnus_full_staff):
    """Happy path: cast Thunder at 2 targets with no charges param →
    defaults to the action's min (2) charges, flat DC 17 CON save, 2d6
    thunder, charges 5 → 3, both targets resolved."""
    magnus = magnus_full_staff
    idx = await _staff_inv_idx(gm_client, magnus["id"])
    t_cid = f"tok_stl1_mag_{magnus['id']}"
    a_cid = "tok_stl1_a"
    b_cid = "tok_stl1_b"
    await _seed_battle(gm_client, [
        _mkc(t_cid, magnus["id"], name=magnus["name"]),
        _mkc(a_cid, None, name="Bandit Alpha"),
        _mkc(b_cid, None, name="Bandit Beta"),
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/use_item_action",
        json={
            "inventory_index": idx,
            "action_key": "thunderclap",
            "target_combatant_ids": [a_cid, b_cid],
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["save_dc"] == 17  # RAW flat DC 17
    assert data["save_ability"] == "CON"
    assert data["dice"] == "2d6"
    assert data["charges_spent"] == 2
    assert data["resource"]["current"] == 3  # 5 → 3
    results = data.get("results") or []
    assert len(results) == 2
    target_ids = {r.get("combatant_id") for r in results}
    assert {a_cid, b_cid}.issubset(target_ids)


async def test_staff_of_thunder_and_lightning_under_min_returns_400(gm_client, magnus_full_staff):
    """Thunder is a fixed 2-charge spend (min=max=2). Asking for 1
    charge → 400."""
    magnus = magnus_full_staff
    idx = await _staff_inv_idx(gm_client, magnus["id"])
    t_cid = f"tok_stl2_mag_{magnus['id']}"
    a_cid = "tok_stl2_a"
    await _seed_battle(gm_client, [
        _mkc(t_cid, magnus["id"], name=magnus["name"]),
        _mkc(a_cid, None, name="Bandit"),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/use_item_action",
        json={
            "inventory_index": idx,
            "action_key": "thunderclap",
            "charges": 1,
            "target_combatant_ids": [a_cid],
        },
    )
    assert resp.status_code == 400, resp.text


async def test_staff_of_thunder_and_lightning_empty_returns_409(gm_client, magnus):
    """Drain the staff below the 2-charge Thunder cost via /sheet-fields,
    then try to cast → 409 insufficient_charges."""
    sheet_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-json",
    )
    sheet = sheet_resp.json().get("sheet") or {}
    resources = list(sheet.get("resources") or [])
    snapshot = [dict(r) if isinstance(r, dict) else r for r in resources]
    drained = [
        {**r, "current": 1} if (isinstance(r, dict) and r.get("key") == _SLUG) else r
        for r in resources
    ]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
        json={"resources": drained},
    )
    try:
        idx = await _staff_inv_idx(gm_client, magnus["id"])
        t_cid = f"tok_stl3_mag_{magnus['id']}"
        await _seed_battle(gm_client, [
            _mkc(t_cid, magnus["id"], name=magnus["name"]),
            _mkc("tok_stl3_a", None, name="Bandit"),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/use_item_action",
            json={
                "inventory_index": idx,
                "action_key": "thunderclap",
                "target_combatant_ids": ["tok_stl3_a"],
            },
        )
        assert resp.status_code == 409, resp.text
        body = resp.json()
        assert body.get("error") == "insufficient_charges"
        assert body.get("current") == 1
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
            json={"resources": snapshot},
        )
