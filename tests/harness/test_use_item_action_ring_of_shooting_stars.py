"""v2.357.0 — magic-items: Ring of Shooting Stars (RAW DMG p.191, very
rare, attunement). The combat "Shooting Stars" mode runs through the
generalized save-for-half Necklace of Fireballs handler — expend 1-3
charges as an action to launch that many glowing motes, each dealing a
DC 15 DEX save for half of 5d4 fire (independent roll per mote, which the
handler already does per target). Pass `charges` = number of motes =
number of target ids. The 6-charge pool regains all at dawn.

Demo home: Zara Emberfire (Sorcerer), seeded equipped+attuned with a
`ring-of-shooting-stars` 6-charge resource. The dancing-lights/light
at-will mode + the ball-lightning mode + the RAW outdoors-at-night
restriction are GM-narrated.

Tests:
  - happy: 3 motes at 3 targets (charges=3) → save_dc=15 DEX, dice=5d4,
    charges_spent=3, resource 6 → 3, all three ids resolved.
  - empty ring (current=0) → 409 insufficient_charges.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_SLUG = "ring-of-shooting-stars"


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
async def zara_full_ring(gm_client, zara):
    """Force-reseed Zara's Ring of Shooting Stars charge counter to
    current=6 via /sheet-fields PATCH. Snapshot + restore on teardown.
    Yields the inventory index resolved by `_slug`."""
    sheet = await _sheet(gm_client, zara["id"])
    resources = list(sheet.get("resources") or [])
    snapshot = [dict(r) if isinstance(r, dict) else r for r in resources]
    for i, r in enumerate(resources):
        if isinstance(r, dict) and r.get("key") == _SLUG:
            resources[i] = {**r, "current": 6, "max": 6}
            break
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/sheet-fields",
        json={"resources": resources},
    )
    idx = _slug_index(sheet.get("inventory") or [], _SLUG)
    assert idx >= 0, "Zara must carry a seeded Ring of Shooting Stars"
    yield {"char": zara, "idx": idx}
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/sheet-fields",
        json={"resources": snapshot},
    )


async def test_ring_shooting_stars_3_motes(gm_client, zara_full_ring):
    """v2.357.0 happy path. Three motes (charges=3) at three targets →
    200, save_dc=15 DEX, dice=5d4, charges_spent=3, resource 6 → 3, all
    three ids resolved."""
    zara = zara_full_ring["char"]
    idx = zara_full_ring["idx"]
    z_cid = f"tok_rss1_zara_{zara['id']}"
    a, b, c = "tok_rss1_a", "tok_rss1_b", "tok_rss1_c"
    await _seed_battle(gm_client, [
        _mkc(z_cid, zara["id"], name=zara["name"]),
        _mkc(a, None, name="Bandit Alpha"),
        _mkc(b, None, name="Bandit Beta"),
        _mkc(c, None, name="Bandit Gamma"),
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/use_item_action",
        json={
            "inventory_index": idx,
            "action_key": "shooting-stars",
            "charges": 3,
            "target_combatant_ids": [a, b, c],
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["item_name"] == "Ring of Shooting Stars"
    assert data["save_dc"] == 15
    assert data["save_ability"] == "DEX"
    assert data["dice"] == "5d4"
    assert data["charges_spent"] == 3
    assert data["resource"]["current"] == 3  # 6 → 3
    results = data.get("results") or []
    assert len(results) == 3
    target_ids = {r.get("combatant_id") for r in results}
    assert {a, b, c}.issubset(target_ids)


async def test_ring_shooting_stars_empty_returns_409(gm_client, zara):
    """v2.357.0: drain the ring to 0 charges via /sheet-fields, then try to
    invoke → 409 insufficient_charges."""
    sheet = await _sheet(gm_client, zara["id"])
    resources = list(sheet.get("resources") or [])
    snapshot = [dict(r) if isinstance(r, dict) else r for r in resources]
    idx = _slug_index(sheet.get("inventory") or [], _SLUG)
    assert idx >= 0, "Zara must carry a seeded Ring of Shooting Stars"
    drained = [
        {**r, "current": 0}
        if (isinstance(r, dict) and r.get("key") == _SLUG)
        else r
        for r in resources
    ]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/sheet-fields",
        json={"resources": drained},
    )
    try:
        z_cid = f"tok_rss2_zara_{zara['id']}"
        await _seed_battle(gm_client, [
            _mkc(z_cid, zara["id"], name=zara["name"]),
            _mkc("tok_rss2_a", None, name="Bandit"),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/use_item_action",
            json={
                "inventory_index": idx,
                "action_key": "shooting-stars",
                "charges": 1,
                "target_combatant_ids": ["tok_rss2_a"],
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
