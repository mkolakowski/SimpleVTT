"""v2.326.0 — magic-items content tail: Gem of Brightness Mode 2 ("beam")
through the same `/use_item_action` endpoint as Wand of Paralysis
(v2.206.0), via the generalized `_use_item_action_wand_of_fear` save-
condition handler. RAW DMG p.172 (uncommon, NO attunement): 50 charges
(no recharge — when depleted, the gem becomes a non-magical 50 gp jewel).
Beam mode spends 1 charge → CON save DC 15 or blinded for 1 minute
(repeat save at end of each of the target's turns).

The handler is content-agnostic: the save DC / ability / condition (key,
label, icon, effects) / feature name / target shape all come from the
catalog `action_def`. The Gem of Brightness defaults override the
Paralysis wand's paralyzed condition with `blinded`; everything else
(charge validation, resource decrement, resolve-save loop, WS broadcast)
is shared.

Demo home: Lyra Sunstrider (Bard) — no attunement, so the gem doesn't
bump her seed-attuned roster. Lyra carries the gem at equipped=True with a
50-charge `gem-of-brightness` resource row (reset: "none", per the RAW
"becomes a 50 gp jewel when depleted" rule).

Tests:
  - happy: beam at 2 targets → save_dc=15, save_ability='CON',
    charges_spent=1, resource drops 50 → 49, results carries both ids.
  - empty gem (current=0) → 409 insufficient_charges.
  - no-attunement contract: the seed inventory item has `equipped: True`
    and no `attuned` flag.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_SLUG = "gem-of-brightness"


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
async def lyra(roster):
    return roster["Lyra Sunstrider"]


@pytest_asyncio.fixture
async def lyra_full_gem(gm_client, lyra):
    """Force-reseed Lyra's Gem of Brightness charge counter to current=50
    via /sheet-fields PATCH. Snapshot + restore on teardown."""
    sheet = await _sheet(gm_client, lyra["id"])
    resources = list(sheet.get("resources") or [])
    snapshot = [dict(r) if isinstance(r, dict) else r for r in resources]
    for i, r in enumerate(resources):
        if isinstance(r, dict) and r.get("key") == _SLUG:
            resources[i] = {**r, "current": 50, "max": 50}
            break
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/sheet-fields",
        json={"resources": resources},
    )
    idx = _slug_index(sheet.get("inventory") or [], _SLUG)
    assert idx >= 0, "Lyra must carry a seeded Gem of Brightness"
    yield {"char": lyra, "idx": idx}
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/sheet-fields",
        json={"resources": snapshot},
    )


async def test_gem_of_brightness_beam_2_targets(gm_client, lyra_full_gem):
    """v2.326.0 happy path. Beam at 2 NPC targets → 200 with results carrying
    both ids, save_dc=15, save_ability='CON', and the charge counter drops
    50 → 49."""
    lyra = lyra_full_gem["char"]
    idx = lyra_full_gem["idx"]
    lyra_cid = f"tok_gob1_lyra_{lyra['id']}"
    a_cid = "tok_gob1_a"
    b_cid = "tok_gob1_b"
    await _seed_battle(gm_client, [
        _mkc(lyra_cid, lyra["id"], name=lyra["name"]),
        _mkc(a_cid, None, name="Bandit Alpha"),
        _mkc(b_cid, None, name="Bandit Beta"),
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/use_item_action",
        json={
            "inventory_index": idx,
            "action_key": "beam",
            "target_combatant_ids": [a_cid, b_cid],
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["item_name"] == "Gem of Brightness"
    assert data["save_dc"] == 15
    assert data["save_ability"] == "CON"
    assert data["charges_spent"] == 1
    assert data["resource"]["current"] == 49  # 50 → 49
    results = data.get("results") or []
    assert len(results) == 2
    target_ids = {r.get("combatant_id") for r in results}
    assert {a_cid, b_cid}.issubset(target_ids)


async def test_gem_of_brightness_empty_returns_409(gm_client, lyra):
    """v2.326.0: drain the gem to 0 charges via /sheet-fields, then try to
    fire the beam → 409 insufficient_charges."""
    sheet = await _sheet(gm_client, lyra["id"])
    resources = list(sheet.get("resources") or [])
    snapshot = [dict(r) if isinstance(r, dict) else r for r in resources]
    idx = _slug_index(sheet.get("inventory") or [], _SLUG)
    assert idx >= 0, "Lyra must carry a seeded Gem of Brightness"
    drained = [
        {**r, "current": 0}
        if (isinstance(r, dict) and r.get("key") == _SLUG)
        else r
        for r in resources
    ]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/sheet-fields",
        json={"resources": drained},
    )

    try:
        lyra_cid = f"tok_gob2_lyra_{lyra['id']}"
        await _seed_battle(gm_client, [
            _mkc(lyra_cid, lyra["id"], name=lyra["name"]),
            _mkc("tok_gob2_a", None, name="Bandit"),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/use_item_action",
            json={
                "inventory_index": idx,
                "action_key": "beam",
                "target_combatant_ids": ["tok_gob2_a"],
            },
        )
        assert resp.status_code == 409, resp.text
        body = resp.json()
        assert body.get("error") == "insufficient_charges"
        assert body.get("current") == 0
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/sheet-fields",
            json={"resources": snapshot},
        )


async def test_gem_of_brightness_no_attunement_required(gm_client, lyra):
    """No-attunement contract — the seed inventory entry has `equipped:
    True` and no `attuned: True` flag, matching the RAW no-attunement
    contract for the gem."""
    sheet = await _sheet(gm_client, lyra["id"])
    inv = sheet.get("inventory") or []
    gem = next(
        (it for it in inv
         if isinstance(it, dict) and it.get("_slug") == _SLUG),
        None,
    )
    assert gem is not None, "Lyra should carry the gem"
    assert gem.get("equipped") is True
    assert not gem.get("attuned"), (
        f"gem should grant its effect un-attuned, got: {gem!r}"
    )
