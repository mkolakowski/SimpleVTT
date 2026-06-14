"""v2.268.0 — charged-items Phase 2: Staff of Swarming Insects (RAW DMG
p.202, rare, attunement): 10 charges; casts giant insect (4) or insect
plague (5) "using your spell save DC". v1 ships the marquee Insect
Plague action through the generalized save-for-half AoE-damage handler
(the same path as the Staff of Fire / Frost / Necklace of Fireballs):

  - the save DC honours the "spell" sentinel (resolved from the
    wielder's sheet — Mira's spell save DC = 14),
  - the dice / damage type / charge cost / feature label all come from
    the catalog action_def (4d10 piercing, CON save),
  - when ``charges`` is omitted the spend defaults to the action's
    ``min_charges`` (Insect Plague is a fixed 5-charge spend, no upcast).

Demo fixture: Mira Greenleaf (Wood Elf Druid Lv 5, WIS 17, prof +3 →
spell save DC 14) carries an equipped + attuned Staff of Swarming
Insects + a 10-charge resource row at key ``staff-of-swarming-insects``.

Tests:
  - happy path: Insect Plague at 2 targets (no charges param) →
    save_dc=14 CON, dice=4d10, charges_spent=5, resource 10 → 5, both
    ids resolved
  - under min charges (1 < 5) → 400
  - empty staff (drained below 5) → 409 insufficient_charges
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_SLUG = "staff-of-swarming-insects"


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
    raise AssertionError("Mira has no staff-of-swarming-insects inventory item")


@pytest_asyncio.fixture
async def mira(roster):
    return roster["Mira Greenleaf"]


@pytest_asyncio.fixture
async def mira_full_staff(gm_client, mira):
    """Force-reseed Mira's Staff of Swarming Insects to a full 10
    charges, restoring the snapshot on teardown."""
    sheet_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/sheet-json",
    )
    sheet = sheet_resp.json().get("sheet") or {}
    resources = list(sheet.get("resources") or [])
    snapshot = [dict(r) if isinstance(r, dict) else r for r in resources]
    for i, r in enumerate(resources):
        if isinstance(r, dict) and r.get("key") == _SLUG:
            resources[i] = {**r, "current": 10, "max": 10}
            break
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/sheet-fields",
        json={"resources": resources},
    )
    yield mira
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/sheet-fields",
        json={"resources": snapshot},
    )


async def test_swarming_insects_insect_plague_2_targets(gm_client, mira_full_staff):
    """Happy path: cast Insect Plague at 2 targets with no charges param →
    defaults to the action's min (5) charges, DC = Mira's spell save DC
    (14), 4d10 piercing, charges 10 → 5, both targets resolved."""
    mira = mira_full_staff
    idx = await _staff_inv_idx(gm_client, mira["id"])
    m_cid = f"tok_ssi1_mira_{mira['id']}"
    a_cid = "tok_ssi1_a"
    b_cid = "tok_ssi1_b"
    await _seed_battle(gm_client, [
        _mkc(m_cid, mira["id"], name=mira["name"]),
        _mkc(a_cid, None, name="Bandit Alpha"),
        _mkc(b_cid, None, name="Bandit Beta"),
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/use_item_action",
        json={
            "inventory_index": idx,
            "action_key": "cast-insect-plague",
            "target_combatant_ids": [a_cid, b_cid],
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["save_dc"] == 14  # Mira's spell save DC (8 + 3 prof + 3 WIS)
    assert data["save_ability"] == "CON"
    assert data["dice"] == "4d10"
    assert data["charges_spent"] == 5
    assert data["resource"]["current"] == 5  # 10 → 5
    results = data.get("results") or []
    assert len(results) == 2
    target_ids = {r.get("combatant_id") for r in results}
    assert {a_cid, b_cid}.issubset(target_ids)


async def test_swarming_insects_under_min_returns_400(gm_client, mira_full_staff):
    """Insect Plague is a fixed 5-charge spend (min=max=5). Asking for 1
    charge → 400."""
    mira = mira_full_staff
    idx = await _staff_inv_idx(gm_client, mira["id"])
    m_cid = f"tok_ssi2_mira_{mira['id']}"
    a_cid = "tok_ssi2_a"
    await _seed_battle(gm_client, [
        _mkc(m_cid, mira["id"], name=mira["name"]),
        _mkc(a_cid, None, name="Bandit"),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/use_item_action",
        json={
            "inventory_index": idx,
            "action_key": "cast-insect-plague",
            "charges": 1,
            "target_combatant_ids": [a_cid],
        },
    )
    assert resp.status_code == 400, resp.text


async def test_swarming_insects_empty_returns_409(gm_client, mira):
    """Drain the staff below the 5-charge Insect Plague cost via
    /sheet-fields, then try to cast → 409 insufficient_charges."""
    sheet_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/sheet-json",
    )
    sheet = sheet_resp.json().get("sheet") or {}
    resources = list(sheet.get("resources") or [])
    snapshot = [dict(r) if isinstance(r, dict) else r for r in resources]
    drained = [
        {**r, "current": 4} if (isinstance(r, dict) and r.get("key") == _SLUG) else r
        for r in resources
    ]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/sheet-fields",
        json={"resources": drained},
    )
    try:
        idx = await _staff_inv_idx(gm_client, mira["id"])
        m_cid = f"tok_ssi3_mira_{mira['id']}"
        await _seed_battle(gm_client, [
            _mkc(m_cid, mira["id"], name=mira["name"]),
            _mkc("tok_ssi3_a", None, name="Bandit"),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/use_item_action",
            json={
                "inventory_index": idx,
                "action_key": "cast-insect-plague",
                "target_combatant_ids": ["tok_ssi3_a"],
            },
        )
        assert resp.status_code == 409, resp.text
        body = resp.json()
        assert body.get("error") == "insufficient_charges"
        assert body.get("current") == 4
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/sheet-fields",
            json={"resources": snapshot},
        )
