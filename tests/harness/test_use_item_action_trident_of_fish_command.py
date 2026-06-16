"""v2.352.0 — magic-items: Trident of Fish Command (RAW DMG p.205,
uncommon, attunement) through the `/use_item_action` endpoint + the
generalized `_use_item_action_wand_of_fear` save-condition handler. Third
Bucket-A charge-cast item off the v2.344.5 triage — the Staff of Charming
single-target `charmed` shape (dominate beast), 3 charges. An action
casts dominate beast (DC 15 WIS) on one beast → charmed for the
concentration duration.

Demo home: Mira Greenleaf (Circle of the Moon Druid), seeded equipped +
attuned with a `trident-of-fish-command` 3-charge resource (the
`/use_item_action` path gates on `attuned` for attunement items). RAW
"only a beast with an innate swimming speed" + the you-control-its-
actions concentration are GM-narrated; v1 installs charmed on a failed
save. The item index + resource row are looked up by `_slug` / key.

Tests:
  - happy: cast-dominate-beast at 1 target → save_dc=15, save_ability=
    'WIS', charges_spent=1, resource 3 → 2, the id in results.
  - empty trident (current=0) → 409 insufficient_charges.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_SLUG = "trident-of-fish-command"


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
        "creature_type": "beast",
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
async def mira(roster):
    return roster["Mira Greenleaf"]


@pytest_asyncio.fixture
async def mira_full_trident(gm_client, mira):
    """Force-reseed Mira's Trident of Fish Command charge counter to
    current=3 via /sheet-fields PATCH. Snapshot + restore on teardown.
    Yields the inventory index resolved by `_slug`."""
    sheet = await _sheet(gm_client, mira["id"])
    resources = list(sheet.get("resources") or [])
    snapshot = [dict(r) if isinstance(r, dict) else r for r in resources]
    for i, r in enumerate(resources):
        if isinstance(r, dict) and r.get("key") == _SLUG:
            resources[i] = {**r, "current": 3, "max": 3}
            break
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/sheet-fields",
        json={"resources": resources},
    )
    idx = _slug_index(sheet.get("inventory") or [], _SLUG)
    assert idx >= 0, "Mira must carry a seeded Trident of Fish Command"
    yield {"char": mira, "idx": idx}
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/sheet-fields",
        json={"resources": snapshot},
    )


async def test_trident_dominate_beast_one_target(gm_client, mira_full_trident):
    """v2.352.0 happy path. Dominate beast at 1 NPC beast target → 200 with
    the id in results, save_dc=15, save_ability='WIS', and the charge
    counter drops 3 → 2."""
    mira = mira_full_trident["char"]
    idx = mira_full_trident["idx"]
    mira_cid = f"tok_tfc1_mira_{mira['id']}"
    beast_cid = "tok_tfc1_beast"
    await _seed_battle(gm_client, [
        _mkc(mira_cid, mira["id"], name=mira["name"]),
        _mkc(beast_cid, None, name="Giant Crab"),
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/use_item_action",
        json={
            "inventory_index": idx,
            "action_key": "cast-dominate-beast",
            "target_combatant_ids": [beast_cid],
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["item_name"] == "Trident of Fish Command"
    assert data["save_dc"] == 15
    assert data["save_ability"] == "WIS"
    assert data["charges_spent"] == 1
    assert data["resource"]["current"] == 2  # 3 → 2
    results = data.get("results") or []
    assert len(results) == 1
    assert results[0].get("combatant_id") == beast_cid


async def test_trident_empty_returns_409(gm_client, mira):
    """v2.352.0: drain the trident to 0 charges via /sheet-fields, then try
    to invoke → 409 insufficient_charges."""
    sheet = await _sheet(gm_client, mira["id"])
    resources = list(sheet.get("resources") or [])
    snapshot = [dict(r) if isinstance(r, dict) else r for r in resources]
    idx = _slug_index(sheet.get("inventory") or [], _SLUG)
    assert idx >= 0, "Mira must carry a seeded Trident of Fish Command"
    drained = [
        {**r, "current": 0}
        if (isinstance(r, dict) and r.get("key") == _SLUG)
        else r
        for r in resources
    ]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/sheet-fields",
        json={"resources": drained},
    )
    try:
        mira_cid = f"tok_tfc2_mira_{mira['id']}"
        await _seed_battle(gm_client, [
            _mkc(mira_cid, mira["id"], name=mira["name"]),
            _mkc("tok_tfc2_beast", None, name="Giant Crab"),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/use_item_action",
            json={
                "inventory_index": idx,
                "action_key": "cast-dominate-beast",
                "target_combatant_ids": ["tok_tfc2_beast"],
            },
        )
        assert resp.status_code == 409, resp.text
        body = resp.json()
        assert body.get("error") == "insufficient_charges"
        assert body.get("current") == 0
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/sheet-fields",
            json={"resources": snapshot},
        )
