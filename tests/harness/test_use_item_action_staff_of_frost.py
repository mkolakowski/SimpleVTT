"""v2.267.0 — charged-items Phase 2: Staff of Frost (RAW DMG p.202, very
rare, attunement): 10 charges; casts cone of cold (5), fog cloud (1),
ice storm (4), or wall of ice (4) "using your spell save DC". v1 ships
the marquee Cone of Cold action through the generalized save-for-half
AoE-damage handler (the same path as the Staff of Fire / Necklace of
Fireballs):

  - the save DC honours the "spell" sentinel (resolved from the
    wielder's sheet — Thalindra's spell save DC = 14),
  - the dice / damage type / charge cost / feature label all come from
    the catalog action_def (8d8 cold, CON save),
  - when ``charges`` is omitted the spend defaults to the action's
    ``min_charges`` (Cone of Cold is a fixed 5-charge spend, no upcast).

Demo fixture: Thalindra Moonwhisper (Elf Wizard Lv 7, INT 16, prof +3 →
spell save DC 14) carries an equipped + attuned Staff of Frost + a
10-charge resource row at key ``staff-of-frost``.

Tests:
  - happy path: Cone of Cold at 2 targets (no charges param) →
    save_dc=14 CON, dice=8d8, charges_spent=5, resource 10 → 5, both
    ids resolved
  - under min charges (1 < 5) → 400
  - empty staff (drained below 5) → 409 insufficient_charges
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_SLUG = "staff-of-frost"


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
    raise AssertionError("Thalindra has no staff-of-frost inventory item")


@pytest_asyncio.fixture
async def thalindra(roster):
    return roster["Thalindra Moonwhisper"]


@pytest_asyncio.fixture
async def thalindra_full_staff(gm_client, thalindra):
    """Force-reseed Thalindra's Staff of Frost to a full 10 charges,
    restoring the snapshot on teardown."""
    sheet_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-json",
    )
    sheet = sheet_resp.json().get("sheet") or {}
    resources = list(sheet.get("resources") or [])
    snapshot = [dict(r) if isinstance(r, dict) else r for r in resources]
    for i, r in enumerate(resources):
        if isinstance(r, dict) and r.get("key") == _SLUG:
            resources[i] = {**r, "current": 10, "max": 10}
            break
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-fields",
        json={"resources": resources},
    )
    yield thalindra
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-fields",
        json={"resources": snapshot},
    )


async def test_staff_of_frost_cone_of_cold_2_targets(gm_client, thalindra_full_staff):
    """Happy path: cast Cone of Cold at 2 targets with no charges param →
    defaults to the action's min (5) charges, DC = Thalindra's spell save
    DC (14), 8d8 cold, charges 10 → 5, both targets resolved."""
    thalindra = thalindra_full_staff
    idx = await _staff_inv_idx(gm_client, thalindra["id"])
    t_cid = f"tok_sfr1_thal_{thalindra['id']}"
    a_cid = "tok_sfr1_a"
    b_cid = "tok_sfr1_b"
    await _seed_battle(gm_client, [
        _mkc(t_cid, thalindra["id"], name=thalindra["name"]),
        _mkc(a_cid, None, name="Bandit Alpha"),
        _mkc(b_cid, None, name="Bandit Beta"),
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/use_item_action",
        json={
            "inventory_index": idx,
            "action_key": "cast-cone-of-cold",
            "target_combatant_ids": [a_cid, b_cid],
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["save_dc"] == 14  # Thalindra's spell save DC (8 + 3 prof + 3 INT)
    assert data["save_ability"] == "CON"
    assert data["dice"] == "8d8"
    assert data["charges_spent"] == 5
    assert data["resource"]["current"] == 5  # 10 → 5
    results = data.get("results") or []
    assert len(results) == 2
    target_ids = {r.get("combatant_id") for r in results}
    assert {a_cid, b_cid}.issubset(target_ids)


async def test_staff_of_frost_under_min_returns_400(gm_client, thalindra_full_staff):
    """Cone of Cold is a fixed 5-charge spend (min=max=5). Asking for 1
    charge → 400."""
    thalindra = thalindra_full_staff
    idx = await _staff_inv_idx(gm_client, thalindra["id"])
    t_cid = f"tok_sfr2_thal_{thalindra['id']}"
    a_cid = "tok_sfr2_a"
    await _seed_battle(gm_client, [
        _mkc(t_cid, thalindra["id"], name=thalindra["name"]),
        _mkc(a_cid, None, name="Bandit"),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/use_item_action",
        json={
            "inventory_index": idx,
            "action_key": "cast-cone-of-cold",
            "charges": 1,
            "target_combatant_ids": [a_cid],
        },
    )
    assert resp.status_code == 400, resp.text


async def test_staff_of_frost_empty_returns_409(gm_client, thalindra):
    """Drain the staff below the 5-charge Cone of Cold cost via
    /sheet-fields, then try to cast → 409 insufficient_charges."""
    sheet_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-json",
    )
    sheet = sheet_resp.json().get("sheet") or {}
    resources = list(sheet.get("resources") or [])
    snapshot = [dict(r) if isinstance(r, dict) else r for r in resources]
    drained = [
        {**r, "current": 4} if (isinstance(r, dict) and r.get("key") == _SLUG) else r
        for r in resources
    ]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-fields",
        json={"resources": drained},
    )
    try:
        idx = await _staff_inv_idx(gm_client, thalindra["id"])
        t_cid = f"tok_sfr3_thal_{thalindra['id']}"
        await _seed_battle(gm_client, [
            _mkc(t_cid, thalindra["id"], name=thalindra["name"]),
            _mkc("tok_sfr3_a", None, name="Bandit"),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/use_item_action",
            json={
                "inventory_index": idx,
                "action_key": "cast-cone-of-cold",
                "target_combatant_ids": ["tok_sfr3_a"],
            },
        )
        assert resp.status_code == 409, resp.text
        body = resp.json()
        assert body.get("error") == "insufficient_charges"
        assert body.get("current") == 4
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-fields",
            json={"resources": snapshot},
        )
