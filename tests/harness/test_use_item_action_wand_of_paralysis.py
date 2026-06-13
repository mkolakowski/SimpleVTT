"""v2.206.0 — magic-items-automation content tail: Wand of Paralysis
through the same `/use_item_action` endpoint as the Wand of Fear
(v2.159.11), via the generalized `_use_item_action_wand_of_fear`
save-condition handler. RAW DMG p.213 (rare, attunement): 7 charges
(regain 1d6+1 at dawn), spend 1 to fire a paralysis ray at one creature
within 60 ft — DC 15 CON save or Paralyzed for 1 minute (repeat save at
the end of each of its turns).

The handler is content-agnostic: the save DC / ability / condition
(key, label, icon, effects) / feature name / target shape all come from
the catalog `action_def`. The Wand of Paralysis defaults override the
Fear wand's WIS→frightened cone with CON→paralyzed ray; everything else
(charge validation, resource decrement, resolve-save loop, WS broadcast)
is shared.

Demo home: Magnus Hexbinder (Warlock Lv 5) — already carries the Wand of
Fear, so this is his second attuned wand (2/3 against the RAW cap). The
wand index is looked up by `_slug` rather than hardcoded because Magnus's
inventory grew across the potion tail.

Tests:
  - happy: cast at 2 targets → save_dc=15, save_ability='CON',
    charges_spent=1, resource drops 7 → 6, results carries both ids.
  - over-cap charges (charges=2 when max=1) → 400.
  - empty wand (current=0) → 409 insufficient_charges.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


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
async def magnus(roster):
    return roster["Magnus Hexbinder"]


@pytest_asyncio.fixture
async def magnus_paralysis_wand(gm_client, magnus):
    """Force-reseed Magnus's Wand of Paralysis charge counter to
    current=7 via /sheet-fields PATCH. Snapshot + restore on teardown so
    downstream tests don't see a drained wand. Yields the inventory
    index resolved by `_slug`."""
    sheet = await _sheet(gm_client, magnus["id"])
    resources = list(sheet.get("resources") or [])
    snapshot = [dict(r) if isinstance(r, dict) else r for r in resources]
    for i, r in enumerate(resources):
        if isinstance(r, dict) and r.get("key") == "wand-of-paralysis":
            resources[i] = {**r, "current": 7, "max": 7}
            break
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
        json={"resources": resources},
    )
    idx = _slug_index(sheet.get("inventory") or [], "wand-of-paralysis")
    assert idx >= 0, "Magnus must carry a seeded Wand of Paralysis"
    yield {"char": magnus, "idx": idx}
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
        json={"resources": snapshot},
    )


async def test_wand_of_paralysis_cast_2_targets(
    gm_client, magnus_paralysis_wand,
):
    """v2.206.0 happy path. Cast at 2 NPC targets → 200 with results
    carrying both ids, save_dc=15, save_ability='CON', and the charge
    counter drops 7 → 6."""
    magnus = magnus_paralysis_wand["char"]
    idx = magnus_paralysis_wand["idx"]
    magnus_cid = f"tok_wop1_magnus_{magnus['id']}"
    a_cid = "tok_wop1_a"
    b_cid = "tok_wop1_b"
    await _seed_battle(gm_client, [
        _mkc(magnus_cid, magnus["id"], name=magnus["name"]),
        _mkc(a_cid, None, name="Bandit Alpha"),
        _mkc(b_cid, None, name="Bandit Beta"),
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/use_item_action",
        json={
            "inventory_index": idx,
            "action_key": "cast-paralysis",
            "target_combatant_ids": [a_cid, b_cid],
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["item_name"] == "Wand of Paralysis"
    assert data["save_dc"] == 15
    assert data["save_ability"] == "CON"
    assert data["charges_spent"] == 1
    assert data["resource"]["current"] == 6  # 7 → 6
    results = data.get("results") or []
    assert len(results) == 2
    target_ids = {r.get("combatant_id") for r in results}
    assert {a_cid, b_cid}.issubset(target_ids)


async def test_wand_of_paralysis_over_cap_returns_400(
    gm_client, magnus_paralysis_wand,
):
    """v2.206.0: charges=2 when catalog max=1 → 400 (the shared
    min/max charge validator)."""
    magnus = magnus_paralysis_wand["char"]
    idx = magnus_paralysis_wand["idx"]
    magnus_cid = f"tok_wop2_magnus_{magnus['id']}"
    a_cid = "tok_wop2_a"
    await _seed_battle(gm_client, [
        _mkc(magnus_cid, magnus["id"], name=magnus["name"]),
        _mkc(a_cid, None, name="Bandit"),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/use_item_action",
        json={
            "inventory_index": idx,
            "action_key": "cast-paralysis",
            "charges": 2,
            "target_combatant_ids": [a_cid],
        },
    )
    assert resp.status_code == 400, resp.text


async def test_wand_of_paralysis_empty_returns_409(
    gm_client, magnus,
):
    """v2.206.0: drain the wand to 0 charges via /sheet-fields, then try
    to cast → 409 insufficient_charges."""
    sheet = await _sheet(gm_client, magnus["id"])
    resources = list(sheet.get("resources") or [])
    snapshot = [dict(r) if isinstance(r, dict) else r for r in resources]
    idx = _slug_index(sheet.get("inventory") or [], "wand-of-paralysis")
    assert idx >= 0, "Magnus must carry a seeded Wand of Paralysis"
    drained = [
        {**r, "current": 0}
        if (isinstance(r, dict) and r.get("key") == "wand-of-paralysis")
        else r
        for r in resources
    ]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
        json={"resources": drained},
    )

    try:
        magnus_cid = f"tok_wop3_magnus_{magnus['id']}"
        await _seed_battle(gm_client, [
            _mkc(magnus_cid, magnus["id"], name=magnus["name"]),
            _mkc("tok_wop3_a", None, name="Bandit"),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/use_item_action",
            json={
                "inventory_index": idx,
                "action_key": "cast-paralysis",
                "target_combatant_ids": ["tok_wop3_a"],
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
