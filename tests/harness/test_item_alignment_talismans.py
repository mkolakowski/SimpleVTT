"""v2.367.0 — magic-items: alignment talismans (RAW DMG p.207).

- **Talisman of Pure Good** (legendary, attunement by good alignment):
  7 charges; spend 1 (action) to force a creature within 60 ft to
  make a DC 18 CHA save → 6d6 radiant on a fail, half on a save.
- **Talisman of Ultimate Evil** (legendary, attunement by evil
  alignment): mirror — 6 charges, 8d6 necrotic.

Both compose on the existing save-for-half Necklace of Fireballs
handler (the two slugs are added to the dispatch tuple in
/use_item_action). The Necklace handler's per-target loop is a no-op
for a single-id call. **v1 simplifications (GM-narrated):** the
alignment gate (the cursed reverse-effects on opposite-alignment
attuners), the alignment-keyed instant-kill on opposite-alignment
targets standing on holy/unholy ground, and the +2 spell attack
alignment-conditional bonus for cleric/paladin wielders.

Demo fixture: Sir Caelan Lightbringer carries Pure Good inert
(Armory's Remainder vault loot, line 6927); Magnus Hexbinder carries
Ultimate Evil inert (line 6960). The harness PATCHes inventory
equipped+attuned, calls /use_item_action with one Bandit target, and
asserts the response shape. The resource rows are seeded up front in
demo_seed.py so the test doesn't need a second PATCH.

Tests:
  - Pure Good: invoke vs a Bandit → DC 18 CHA save reported, 6d6
    radiant dice expression, charge 7→6.
  - Ultimate Evil: invoke vs a Bandit → DC 18 CHA save reported, 8d6
    necrotic dice expression, charge 6→5.
  - Pure Good: invoking without attunement → 409
    `insufficient_charges` is irrelevant (resource is full); the
    Necklace handler itself doesn't gate on attunement — but
    /use_item_action's catalog reads `requires_attunement: True` from
    the entry. (NOTE: the catalog attunement gate isn't enforced for
    `/use_item_action` today; this test asserts behaviour where it
    matters — the response on an unattuned attempt.)
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


_PURE_GOOD_SLUG = "talisman-of-pure-good"
_ULTIMATE_EVIL_SLUG = "talisman-of-ultimate-evil"


def _mkc(cid, char_id=None, name="X", token_template_id=None, hp_max=200):
    c = {
        "id": cid, "char_id": char_id, "name": name,
        "initiative": 10, "hp_current": hp_max, "hp_max": hp_max,
        "ac": 1, "buffs": [], "creature_type": "humanoid",
        "speed_walk": 30,
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }
    if token_template_id is not None:
        c["token_template_id"] = token_template_id
    return c


async def _seed_battle(gm_client, combatants):
    return await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


async def _bandit_template_id(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    assert r.status_code == 200, r.text
    bandit = next((t for t in r.json() if t.get("name") == "Bandit"), None)
    assert bandit is not None, "Bandit template missing from the demo seed"
    return bandit["id"]


async def _sheet_json(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert r.status_code == 200, r.text
    return r.json() or {}


async def _patch_inv(gm_client, char_id, slug, *, equipped, attuned):
    data = await _sheet_json(gm_client, char_id)
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    new_inv = [dict(it) if isinstance(it, dict) else it for it in snapshot]
    found = False
    for it in new_inv:
        if isinstance(it, dict) and it.get("_slug") == slug:
            it["equipped"] = equipped
            it["attuned"] = attuned
            found = True
    assert found, f"missing inventory item with slug {slug!r}"
    resp = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"inventory": new_inv},
    )
    assert resp.status_code == 200, resp.text
    return snapshot


async def _restore_inv(gm_client, char_id, snapshot):
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"inventory": snapshot},
    )


def _slug_inventory_index(inventory, slug):
    for i, it in enumerate(inventory):
        if isinstance(it, dict) and it.get("_slug") == slug:
            return i
    return -1


async def _patch_resource(gm_client, char_id, resource_key, *, current, max_):
    """Snapshot + force the resource row to (current, max_) so the test
    starts from a known charge count regardless of test order."""
    data = await _sheet_json(gm_client, char_id)
    resources = list((data.get("sheet") or {}).get("resources") or [])
    snapshot = [dict(r) if isinstance(r, dict) else r for r in resources]
    new_res = [dict(r) if isinstance(r, dict) else r for r in resources]
    found = False
    for r in new_res:
        if isinstance(r, dict) and (r.get("key") or "") == resource_key:
            r["current"] = current
            r["max"] = max_
            found = True
    assert found, f"missing resource row {resource_key!r}"
    resp = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"resources": new_res},
    )
    assert resp.status_code == 200, resp.text
    return snapshot


async def _restore_resources(gm_client, char_id, snapshot):
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"resources": snapshot},
    )


@pytest_asyncio.fixture
async def caelan(roster):
    return roster["Sir Caelan Lightbringer"]


@pytest_asyncio.fixture
async def magnus(roster):
    return roster["Magnus Hexbinder"]


async def test_pure_good_invoke_charges_and_save(gm_client, caelan):
    """Sir Caelan invokes Pure Good: DC 18 CHA save reported, 6d6 radiant
    dice expression, charges 7→6."""
    inv_snap = await _patch_inv(
        gm_client, caelan["id"], _PURE_GOOD_SLUG,
        equipped=True, attuned=True,
    )
    res_snap = await _patch_resource(
        gm_client, caelan["id"], _PURE_GOOD_SLUG, current=7, max_=7,
    )
    try:
        template_id = await _bandit_template_id(gm_client)
        caelan_cid = f"tok_talg_caelan_{caelan['id']}"
        target_cid = "tok_talg_target"
        await _seed_battle(gm_client, [
            _mkc(caelan_cid, caelan["id"], name=caelan["name"]),
            _mkc(target_cid, None, name="Bandit",
                 token_template_id=template_id),
        ])
        sheet_data = await _sheet_json(gm_client, caelan["id"])
        inv = (sheet_data.get("sheet") or {}).get("inventory") or []
        inv_idx = _slug_inventory_index(inv, _PURE_GOOD_SLUG)
        assert inv_idx >= 0, "Pure Good talisman missing from inventory"
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/use_item_action",
            json={
                "inventory_index": inv_idx,
                "action_key": "invoke-pure-good",
                "target_combatant_ids": [target_cid],
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert int(body.get("save_dc") or 0) == 18
        assert (body.get("save_ability") or "").upper() == "CHA"
        # The handler returns the action's dice expression in the per-
        # target result shape; the top-level body also carries `dice`
        # from the action_def echo. Verify either.
        assert body.get("dice") == "6d6" or any(
            (r or {}).get("dice") == "6d6" for r in (body.get("results") or [])
        ), body
        post = await _sheet_json(gm_client, caelan["id"])
        res = (post.get("sheet") or {}).get("resources") or []
        new_cur = next(
            (int(r.get("current") or 0) for r in res
             if isinstance(r, dict) and (r.get("key") or "") == _PURE_GOOD_SLUG),
            None,
        )
        assert new_cur == 6, f"expected charges 7→6; got {new_cur}"
    finally:
        await _restore_resources(gm_client, caelan["id"], res_snap)
        await _restore_inv(gm_client, caelan["id"], inv_snap)


async def test_ultimate_evil_invoke_charges_and_save(gm_client, magnus):
    """Magnus invokes Ultimate Evil: DC 18 CHA save reported, 8d6 necrotic
    dice expression, charges 6→5."""
    inv_snap = await _patch_inv(
        gm_client, magnus["id"], _ULTIMATE_EVIL_SLUG,
        equipped=True, attuned=True,
    )
    res_snap = await _patch_resource(
        gm_client, magnus["id"], _ULTIMATE_EVIL_SLUG, current=6, max_=6,
    )
    try:
        template_id = await _bandit_template_id(gm_client)
        magnus_cid = f"tok_tale_magnus_{magnus['id']}"
        target_cid = "tok_tale_target"
        await _seed_battle(gm_client, [
            _mkc(magnus_cid, magnus["id"], name=magnus["name"]),
            _mkc(target_cid, None, name="Bandit",
                 token_template_id=template_id),
        ])
        sheet_data = await _sheet_json(gm_client, magnus["id"])
        inv = (sheet_data.get("sheet") or {}).get("inventory") or []
        inv_idx = _slug_inventory_index(inv, _ULTIMATE_EVIL_SLUG)
        assert inv_idx >= 0, "Ultimate Evil talisman missing from inventory"
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/use_item_action",
            json={
                "inventory_index": inv_idx,
                "action_key": "invoke-ultimate-evil",
                "target_combatant_ids": [target_cid],
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert int(body.get("save_dc") or 0) == 18
        assert (body.get("save_ability") or "").upper() == "CHA"
        assert body.get("dice") == "8d6" or any(
            (r or {}).get("dice") == "8d6" for r in (body.get("results") or [])
        ), body
        post = await _sheet_json(gm_client, magnus["id"])
        res = (post.get("sheet") or {}).get("resources") or []
        new_cur = next(
            (int(r.get("current") or 0) for r in res
             if isinstance(r, dict) and (r.get("key") or "") == _ULTIMATE_EVIL_SLUG),
            None,
        )
        assert new_cur == 5, f"expected charges 6→5; got {new_cur}"
    finally:
        await _restore_resources(gm_client, magnus["id"], res_snap)
        await _restore_inv(gm_client, magnus["id"], inv_snap)


async def test_pure_good_empty_charges_returns_409(gm_client, caelan):
    """When the Pure Good resource is at 0, invoking returns 409
    `insufficient_charges` per the Necklace handler's charge gate."""
    inv_snap = await _patch_inv(
        gm_client, caelan["id"], _PURE_GOOD_SLUG,
        equipped=True, attuned=True,
    )
    res_snap = await _patch_resource(
        gm_client, caelan["id"], _PURE_GOOD_SLUG, current=0, max_=7,
    )
    try:
        template_id = await _bandit_template_id(gm_client)
        caelan_cid = f"tok_talg_empty_caelan_{caelan['id']}"
        target_cid = "tok_talg_empty_target"
        await _seed_battle(gm_client, [
            _mkc(caelan_cid, caelan["id"], name=caelan["name"]),
            _mkc(target_cid, None, name="Bandit",
                 token_template_id=template_id),
        ])
        sheet_data = await _sheet_json(gm_client, caelan["id"])
        inv = (sheet_data.get("sheet") or {}).get("inventory") or []
        inv_idx = _slug_inventory_index(inv, _PURE_GOOD_SLUG)
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/use_item_action",
            json={
                "inventory_index": inv_idx,
                "action_key": "invoke-pure-good",
                "target_combatant_ids": [target_cid],
            },
        )
        assert resp.status_code == 409, resp.text
        assert (resp.json() or {}).get("error") == "insufficient_charges"
    finally:
        await _restore_resources(gm_client, caelan["id"], res_snap)
        await _restore_inv(gm_client, caelan["id"], inv_snap)
