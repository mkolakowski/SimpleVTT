"""v2.269.0 — charged-items Phase 3: Ring of the Ram (RAW DMG p.193,
rare, attunement). The FIRST non-spell charge action — the ``ram-strike``
action routes through the new ``action_kind: "attack"`` handler instead
of a catalogued spell cast. It rolls a ranged attack (1d20 + 7 vs the
target's AC) and deals 2d10 force damage *per charge spent* on a hit
(2/4/6d10), decrementing the charge resource by the number spent.

Demo fixture: Garrik Ironside (Fighter) carries an equipped + attuned
Ring of the Ram + a 3-charge resource row at key ``ring-of-the-ram``.

Tests:
  - happy path: 2-charge ram-strike at a low-AC target → ok,
    charges_spent=2, to_hit=7, dice="4d10" (2d10 × 2 charges), resource
    3 → 1, attack resolved vs target AC, damage on a hit
  - over max charges (4 > 3) → 400
  - drained ring (0 charges) → 409 insufficient_charges
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_SLUG = "ring-of-the-ram"


def _mkc(cid, char_id=None, name="X", hp_max=200, ac=1):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": hp_max, "hp_max": hp_max,
        "ac": ac,
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


async def _ring_inv_idx(gm_client, char_id):
    sheet_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    sheet = sheet_resp.json().get("sheet") or {}
    inv = sheet.get("inventory") or []
    for i, it in enumerate(inv):
        if isinstance(it, dict) and it.get("_slug") == _SLUG:
            return i
    raise AssertionError("Garrik has no ring-of-the-ram inventory item")


@pytest_asyncio.fixture
async def garrik(roster):
    return roster["Garrik Ironside"]


@pytest_asyncio.fixture
async def garrik_full_ring(gm_client, garrik):
    """Force-reseed Garrik's Ring of the Ram to a full 3 charges,
    restoring the snapshot on teardown."""
    sheet_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/sheet-json",
    )
    sheet = sheet_resp.json().get("sheet") or {}
    resources = list(sheet.get("resources") or [])
    snapshot = [dict(r) if isinstance(r, dict) else r for r in resources]
    for i, r in enumerate(resources):
        if isinstance(r, dict) and r.get("key") == _SLUG:
            resources[i] = {**r, "current": 3, "max": 3}
            break
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/sheet-fields",
        json={"resources": resources},
    )
    yield garrik
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/sheet-fields",
        json={"resources": snapshot},
    )


async def test_ring_of_the_ram_two_charge_strike(gm_client, garrik_full_ring):
    """Happy path: a 2-charge ram-strike at a low-AC (1) target →
    charges_spent=2, to_hit=7, dice scales to 4d10, resource 3 → 1, the
    attack resolves vs the target's AC and lands damage on a hit."""
    garrik = garrik_full_ring
    idx = await _ring_inv_idx(gm_client, garrik["id"])
    g_cid = f"tok_rotr1_garrik_{garrik['id']}"
    t_cid = "tok_rotr1_t"
    await _seed_battle(gm_client, [
        _mkc(g_cid, garrik["id"], name=garrik["name"]),
        _mkc(t_cid, None, name="Bandit", ac=1),
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/use_item_action",
        json={
            "inventory_index": idx,
            "action_key": "ram-strike",
            "charges": 2,
            "target_combatant_ids": [t_cid],
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["action_kind"] == "attack"
    assert data["charges_spent"] == 2
    assert data["to_hit"] == 7
    assert data["dice"] == "4d10"  # 2d10 per charge × 2 charges
    assert data["damage_type"] == "force"
    assert data["target_combatant_id"] == t_cid
    assert data["target_ac"] == 1
    assert isinstance(data["hit"], bool)
    assert data["resource"]["current"] == 1  # 3 → 1
    # vs AC 1 the only miss is a natural 1; either way the contract holds.
    if data["hit"]:
        assert data["damage"] > 0
    else:
        assert data["damage"] == 0


async def test_ring_of_the_ram_over_max_returns_400(gm_client, garrik_full_ring):
    """Ram-strike spends 1-3 charges (min=1/max=3). Asking for 4 → 400."""
    garrik = garrik_full_ring
    idx = await _ring_inv_idx(gm_client, garrik["id"])
    g_cid = f"tok_rotr2_garrik_{garrik['id']}"
    t_cid = "tok_rotr2_t"
    await _seed_battle(gm_client, [
        _mkc(g_cid, garrik["id"], name=garrik["name"]),
        _mkc(t_cid, None, name="Bandit"),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/use_item_action",
        json={
            "inventory_index": idx,
            "action_key": "ram-strike",
            "charges": 4,
            "target_combatant_ids": [t_cid],
        },
    )
    assert resp.status_code == 400, resp.text


async def test_ring_of_the_ram_empty_returns_409(gm_client, garrik):
    """Drain the ring to 0 charges via /sheet-fields, then try to strike
    → 409 insufficient_charges."""
    sheet_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/sheet-json",
    )
    sheet = sheet_resp.json().get("sheet") or {}
    resources = list(sheet.get("resources") or [])
    snapshot = [dict(r) if isinstance(r, dict) else r for r in resources]
    drained = [
        {**r, "current": 0} if (isinstance(r, dict) and r.get("key") == _SLUG) else r
        for r in resources
    ]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/sheet-fields",
        json={"resources": drained},
    )
    try:
        idx = await _ring_inv_idx(gm_client, garrik["id"])
        g_cid = f"tok_rotr3_garrik_{garrik['id']}"
        await _seed_battle(gm_client, [
            _mkc(g_cid, garrik["id"], name=garrik["name"]),
            _mkc("tok_rotr3_t", None, name="Bandit"),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/use_item_action",
            json={
                "inventory_index": idx,
                "action_key": "ram-strike",
                "target_combatant_ids": ["tok_rotr3_t"],
            },
        )
        assert resp.status_code == 409, resp.text
        body = resp.json()
        assert body.get("error") == "insufficient_charges"
        assert body.get("current") == 0
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/sheet-fields",
            json={"resources": snapshot},
        )
