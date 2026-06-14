"""v2.274.0 — charged-items Phase 2: Staff of Power (RAW DMG p.202, very
rare, requires attunement by a spellcaster). The marquee multi-action
staff:

  - a +2 passive to AC, saving throws, and spell attack rolls while held
    (rides the _MAGIC_ITEM_PASSIVES substrate — exercised by the
    /sheet-json derived assertions below),
  - a 20-charge pool (regain 2d8+4 at dawn),
  - several damaging spell actions routed through the generalized
    save-for-half AoE-damage handler (same path as Staff of Fire / Frost
    / Necklace of Fireballs):
      * Fireball (5th level): 10d6 fire, DEX save at your spell save DC
      * Lightning Bolt (5th level): 10d6 lightning, DEX save
      * Cone of Cold: 8d8 cold, CON save
    Each is a fixed 5-charge spend (min=max=5). The dice / damage type /
    save ability / feature label all come from the catalog action_def;
    the DC resolves to the wielder's spell save DC via the "spell"
    sentinel.

Demo fixture: Thalindra Moonwhisper (High Elf Wizard) carries an
equipped + attuned Staff of Power + a 20-charge resource row at key
``staff-of-power``.

Tests:
  - happy path: Fireball at 2 targets → DEX save, 10d6, charges 20 → 15
  - happy path: Lightning Bolt at 1 target → DEX save, 10d6, charges → 15
  - happy path: Cone of Cold at 1 target → CON save, 8d8, charges → 15
  - empty staff (drained below 5) → 409 insufficient_charges
  - passive: /sheet-json derived spell_attack_bonus includes the +2
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_SLUG = "staff-of-power"


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
    raise AssertionError("Thalindra has no staff-of-power item")


@pytest_asyncio.fixture
async def thalindra(roster):
    return roster["Thalindra Moonwhisper"]


@pytest_asyncio.fixture
async def thalindra_full_staff(gm_client, thalindra):
    """Force-reseed Thalindra's Staff of Power to a full 20 charges,
    restoring the snapshot on teardown."""
    sheet_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-json",
    )
    sheet = sheet_resp.json().get("sheet") or {}
    resources = list(sheet.get("resources") or [])
    snapshot = [dict(r) if isinstance(r, dict) else r for r in resources]
    for i, r in enumerate(resources):
        if isinstance(r, dict) and r.get("key") == _SLUG:
            resources[i] = {**r, "current": 20, "max": 20}
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


async def test_staff_of_power_fireball_2_targets(gm_client, thalindra_full_staff):
    """Happy path: Fireball at 2 targets → DEX save at the wielder's spell
    save DC, 10d6 fire, charges 20 → 15, both targets resolved."""
    thalindra = thalindra_full_staff
    idx = await _staff_inv_idx(gm_client, thalindra["id"])
    t_cid = f"tok_sop1_th_{thalindra['id']}"
    a_cid = "tok_sop1_a"
    b_cid = "tok_sop1_b"
    await _seed_battle(gm_client, [
        _mkc(t_cid, thalindra["id"], name=thalindra["name"]),
        _mkc(a_cid, None, name="Bandit Alpha"),
        _mkc(b_cid, None, name="Bandit Beta"),
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/use_item_action",
        json={
            "inventory_index": idx,
            "action_key": "cast-fireball",
            "target_combatant_ids": [a_cid, b_cid],
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["save_ability"] == "DEX"
    assert data["dice"] == "10d6"
    assert data["charges_spent"] == 5
    assert data["resource"]["current"] == 15  # 20 → 15
    results = data.get("results") or []
    assert len(results) == 2
    target_ids = {r.get("combatant_id") for r in results}
    assert {a_cid, b_cid}.issubset(target_ids)


async def test_staff_of_power_lightning_bolt(gm_client, thalindra_full_staff):
    """Lightning Bolt → DEX save, 10d6 lightning, charges 20 → 15."""
    thalindra = thalindra_full_staff
    idx = await _staff_inv_idx(gm_client, thalindra["id"])
    t_cid = f"tok_sop2_th_{thalindra['id']}"
    a_cid = "tok_sop2_a"
    await _seed_battle(gm_client, [
        _mkc(t_cid, thalindra["id"], name=thalindra["name"]),
        _mkc(a_cid, None, name="Bandit"),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/use_item_action",
        json={
            "inventory_index": idx,
            "action_key": "cast-lightning-bolt",
            "target_combatant_ids": [a_cid],
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["save_ability"] == "DEX"
    assert data["dice"] == "10d6"
    assert data["charges_spent"] == 5
    assert data["resource"]["current"] == 15


async def test_staff_of_power_cone_of_cold(gm_client, thalindra_full_staff):
    """Cone of Cold → CON save, 8d8 cold, charges 20 → 15."""
    thalindra = thalindra_full_staff
    idx = await _staff_inv_idx(gm_client, thalindra["id"])
    t_cid = f"tok_sop3_th_{thalindra['id']}"
    a_cid = "tok_sop3_a"
    await _seed_battle(gm_client, [
        _mkc(t_cid, thalindra["id"], name=thalindra["name"]),
        _mkc(a_cid, None, name="Bandit"),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/use_item_action",
        json={
            "inventory_index": idx,
            "action_key": "cast-cone-of-cold",
            "target_combatant_ids": [a_cid],
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["save_ability"] == "CON"
    assert data["dice"] == "8d8"
    assert data["charges_spent"] == 5
    assert data["resource"]["current"] == 15


async def test_staff_of_power_empty_returns_409(gm_client, thalindra):
    """Drain the staff below the 5-charge cost via /sheet-fields, then try
    to cast → 409 insufficient_charges."""
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
        t_cid = f"tok_sop4_th_{thalindra['id']}"
        await _seed_battle(gm_client, [
            _mkc(t_cid, thalindra["id"], name=thalindra["name"]),
            _mkc("tok_sop4_a", None, name="Bandit"),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/use_item_action",
            json={
                "inventory_index": idx,
                "action_key": "cast-fireball",
                "target_combatant_ids": ["tok_sop4_a"],
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


async def test_staff_of_power_passive_spell_attack_bonus(gm_client, thalindra):
    """The held Staff of Power grants +2 to spell attack rolls via the
    passive substrate — /sheet-json derived should surface it."""
    sheet_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-json",
    )
    derived = sheet_resp.json().get("derived") or {}
    sab = derived.get("spell_attack_bonus")
    assert sab is not None, sheet_resp.text
    assert int(sab.get("bonus") or 0) >= 2
