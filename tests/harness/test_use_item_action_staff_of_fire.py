"""v2.210.0 — magic-items Staff of Fire (RAW DMG p.202, very rare,
attunement): 10 charges; cast burning hands (1), fireball (3), or wall
of fire (4) "using your spell save DC". v1 ships the marquee Fireball
action through the generalized save-for-half AoE-damage handler (the
same path as the Necklace of Fireballs), which this commit makes
content-agnostic:

  - the save DC honours the "spell" sentinel (resolved from the
    wielder's sheet — Zara's spell save DC = 14),
  - the dice / damage type / charge cost / feature label all come from
    the catalog action_def,
  - when ``charges`` is omitted the spend defaults to the action's
    ``min_charges`` (Fireball is a fixed 3-charge spend, no upcast).

Demo fixture: Zara Emberfire (Tiefling Sorcerer Lv 5, spell save DC 14)
carries an equipped + attuned Staff of Fire + a 10-charge resource row
at key ``staff-of-fire``.

Tests:
  - happy path: Fireball at 2 targets (no charges param) → save_dc=14
    DEX, dice=8d6, charges_spent=3, resource 10 → 7, both ids resolved
  - under min charges (1 < 3) → 400
  - empty staff (drained below 3) → 409 insufficient_charges
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


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
        if isinstance(it, dict) and it.get("_slug") == "staff-of-fire":
            return i
    raise AssertionError("Zara has no staff-of-fire inventory item")


@pytest_asyncio.fixture
async def zara(roster):
    return roster["Zara Emberfire"]


@pytest_asyncio.fixture
async def zara_full_staff(gm_client, zara):
    """Force-reseed Zara's Staff of Fire to a full 10 charges, restoring
    the snapshot on teardown."""
    sheet_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/sheet-json",
    )
    sheet = sheet_resp.json().get("sheet") or {}
    resources = list(sheet.get("resources") or [])
    snapshot = [dict(r) if isinstance(r, dict) else r for r in resources]
    for i, r in enumerate(resources):
        if isinstance(r, dict) and r.get("key") == "staff-of-fire":
            resources[i] = {**r, "current": 10, "max": 10}
            break
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/sheet-fields",
        json={"resources": resources},
    )
    yield zara
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/sheet-fields",
        json={"resources": snapshot},
    )


async def test_staff_of_fire_fireball_2_targets(gm_client, zara_full_staff):
    """Happy path: cast Fireball at 2 targets with no charges param →
    defaults to the action's min (3) charges, DC = Zara's spell save DC
    (14), 8d6 fire, charges 10 → 7, both targets resolved."""
    zara = zara_full_staff
    idx = await _staff_inv_idx(gm_client, zara["id"])
    z_cid = f"tok_sof1_zara_{zara['id']}"
    a_cid = "tok_sof1_a"
    b_cid = "tok_sof1_b"
    await _seed_battle(gm_client, [
        _mkc(z_cid, zara["id"], name=zara["name"]),
        _mkc(a_cid, None, name="Bandit Alpha"),
        _mkc(b_cid, None, name="Bandit Beta"),
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/use_item_action",
        json={
            "inventory_index": idx,
            "action_key": "cast-fireball",
            "target_combatant_ids": [a_cid, b_cid],
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["save_dc"] == 14  # Zara's spell save DC (8 + 3 prof + 3 CHA)
    assert data["save_ability"] == "DEX"
    assert data["dice"] == "8d6"
    assert data["charges_spent"] == 3
    assert data["resource"]["current"] == 7  # 10 → 7
    results = data.get("results") or []
    assert len(results) == 2
    target_ids = {r.get("combatant_id") for r in results}
    assert {a_cid, b_cid}.issubset(target_ids)


async def test_staff_of_fire_under_min_returns_400(gm_client, zara_full_staff):
    """Fireball is a fixed 3-charge spend (min=max=3). Asking for 1
    charge → 400."""
    zara = zara_full_staff
    idx = await _staff_inv_idx(gm_client, zara["id"])
    z_cid = f"tok_sof2_zara_{zara['id']}"
    a_cid = "tok_sof2_a"
    await _seed_battle(gm_client, [
        _mkc(z_cid, zara["id"], name=zara["name"]),
        _mkc(a_cid, None, name="Bandit"),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/use_item_action",
        json={
            "inventory_index": idx,
            "action_key": "cast-fireball",
            "charges": 1,
            "target_combatant_ids": [a_cid],
        },
    )
    assert resp.status_code == 400, resp.text


async def test_staff_of_fire_empty_returns_409(gm_client, zara):
    """Drain the staff below the 3-charge Fireball cost via
    /sheet-fields, then try to cast → 409 insufficient_charges."""
    sheet_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/sheet-json",
    )
    sheet = sheet_resp.json().get("sheet") or {}
    resources = list(sheet.get("resources") or [])
    snapshot = [dict(r) if isinstance(r, dict) else r for r in resources]
    drained = [
        {**r, "current": 2} if (isinstance(r, dict) and r.get("key") == "staff-of-fire") else r
        for r in resources
    ]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/sheet-fields",
        json={"resources": drained},
    )
    try:
        idx = await _staff_inv_idx(gm_client, zara["id"])
        z_cid = f"tok_sof3_zara_{zara['id']}"
        await _seed_battle(gm_client, [
            _mkc(z_cid, zara["id"], name=zara["name"]),
            _mkc("tok_sof3_a", None, name="Bandit"),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/use_item_action",
            json={
                "inventory_index": idx,
                "action_key": "cast-fireball",
                "target_combatant_ids": ["tok_sof3_a"],
            },
        )
        assert resp.status_code == 409, resp.text
        body = resp.json()
        assert body.get("error") == "insufficient_charges"
        assert body.get("current") == 2
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/sheet-fields",
            json={"resources": snapshot},
        )
