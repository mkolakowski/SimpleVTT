"""v2.403.0 — magic-items-automation Phase 9.2: the first batch of
charge-tracked announce-only Bucket D items. Four elemental-summoning
items (RAW 1/dawn, no attunement) share the new
`_use_item_action_announce_only` handler:

  - bowl-of-commanding-water-elementals  (on Rowan)
  - brazier-of-commanding-fire-elementals (on Caelan)
  - censer-of-controlling-air-elementals (on Seraphine)
  - stone-of-controlling-earth-elementals (on Krieger)

The mechanical surface is the charge decrement + the broadcast
summary; the actual elemental summon + CHA control check stay GM-
narrated. The tests cover (a) happy-path decrement from 1 → 0 +
return shape, (b) second-call same-day → 409 insufficient_charges,
(c) restoration via long rest.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


# (carrier_name, slug, item_name, initial_charges)
# v2.403.0 ships the first 4 (elemental-summoning quartet — all 1/1).
# v2.403.1 adds 4 more 1/dawn-ish items: cape (1/1), iron-bands (1/1),
# efreeti-bottle (1/1), bag-of-tricks (3/3).
_BATCH = [
    ("Rowan Quickbow", "bowl-of-commanding-water-elementals",
     "Bowl of Commanding Water Elementals", 1),
    ("Sir Caelan Lightbringer", "brazier-of-commanding-fire-elementals",
     "Brazier of Commanding Fire Elementals", 1),
    ("Dame Seraphine Vael", "censer-of-controlling-air-elementals",
     "Censer of Controlling Air Elementals", 1),
    ("Krieger Stonefist", "stone-of-controlling-earth-elementals",
     "Stone of Controlling Earth Elementals", 1),
    ("Lyra Sunstrider", "cape-of-the-mountebank",
     "Cape of the Mountebank", 1),
    ("Krieger Stonefist", "iron-bands-of-binding",
     "Iron Bands of Binding", 1),
    ("Zara Emberfire", "efreeti-bottle",
     "Efreeti Bottle", 1),
    ("Brakka Wildmane", "bag-of-tricks",
     "Bag of Tricks", 3),
]


def _slug_index(inventory, slug):
    for i, it in enumerate(inventory):
        if isinstance(it, dict) and (it.get("_slug") or "") == slug:
            return i
    return -1


async def _sheet(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    return (r.json() or {}).get("sheet") or {}


async def _long_rest(gm_client, char_id):
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )


def _resource_current(sheet, key):
    for r in (sheet.get("resources") or []):
        if isinstance(r, dict) and (r.get("key") or "") == key:
            return int(r.get("current") or 0)
    return None


async def _invoke(gm_client, char_id, inv_idx, action_key, charges=None):
    body = {"inventory_index": inv_idx, "action_key": action_key}
    if charges is not None:
        body["charges"] = charges
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/use_item_action",
        json=body,
    )


async def _patch_inventory_item(gm_client, char_id, slug, **fields):
    """v2.403.2: PATCH inventory item flags (equipped/attuned). For
    vault-loot items that ship inert; the test flips equipped+attuned,
    runs the assertions, then restores. Returns the prior values dict
    so the caller can restore."""
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    sheet = (r.json() or {}).get("sheet") or {}
    inv = list(sheet.get("inventory") or [])
    prior = {}
    for it in inv:
        if isinstance(it, dict) and it.get("_slug") == slug:
            for k in fields:
                prior[k] = it.get(k)
                it[k] = fields[k]
    resp = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"inventory": inv},
    )
    assert resp.status_code == 200, resp.text
    return prior


_ACTION_KEYS = {
    "bowl-of-commanding-water-elementals": "summon-water-elemental",
    "brazier-of-commanding-fire-elementals": "summon-fire-elemental",
    "censer-of-controlling-air-elementals": "summon-air-elemental",
    "stone-of-controlling-earth-elementals": "summon-earth-elemental",
    "cape-of-the-mountebank": "cast-dimension-door",
    "iron-bands-of-binding": "hurl-bands",
    "efreeti-bottle": "release-efreeti",
    "bag-of-tricks": "pull-creature",
}


@pytest_asyncio.fixture
async def fresh_resources(gm_client, roster):
    """Long-rest each carrier so the test starts from each item's full
    pool even if a prior test in the suite spent a charge."""
    seen = set()
    for carrier_name, _, _, _ in _BATCH:
        if carrier_name in seen:
            continue
        seen.add(carrier_name)
        await _long_rest(gm_client, roster[carrier_name]["id"])
    yield
    seen = set()
    for carrier_name, _, _, _ in _BATCH:
        if carrier_name in seen:
            continue
        seen.add(carrier_name)
        await _long_rest(gm_client, roster[carrier_name]["id"])


async def test_announce_only_items_decrement_charge(
    gm_client, roster, fresh_resources,
):
    """v2.403.0 + v2.403.1 happy path. For each Bucket D item on the
    `_use_item_action_announce_only` substrate: invoke → 200 with
    charges_spent=1, resource.current = initial-1, item_name
    populated. Asserts the charge actually decrements on the sheet."""
    for carrier_name, slug, item_name, initial in _BATCH:
        char = roster[carrier_name]
        sheet = await _sheet(gm_client, char["id"])
        idx = _slug_index(sheet.get("inventory") or [], slug)
        assert idx >= 0, f"{carrier_name} must carry seeded {slug}"
        assert _resource_current(sheet, slug) == initial, \
            f"{slug} should start at {initial}/{initial} for {carrier_name}"

        resp = await _invoke(gm_client, char["id"], idx,
                             _ACTION_KEYS[slug])
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["ok"] is True
        assert data["item_name"] == item_name
        assert data["charges_spent"] == 1
        assert data["resource"]["current"] == initial - 1
        assert data["resource"]["max"] == initial
        assert data["resource"]["key"] == slug

        # And the persisted sheet really shows the new count.
        sheet_after = await _sheet(gm_client, char["id"])
        assert _resource_current(sheet_after, slug) == initial - 1


async def test_second_use_same_day_returns_409(
    gm_client, roster, fresh_resources,
):
    """v2.403.0 error path. Invoking a 1/dawn item a second time before
    a rest → 409 insufficient_charges with current=0."""
    # Use Rowan's bowl (1/1) so two invocations exhausts the pool.
    carrier_name, slug, _, _ = _BATCH[0]
    char = roster[carrier_name]

    sheet = await _sheet(gm_client, char["id"])
    idx = _slug_index(sheet.get("inventory") or [], slug)
    first = await _invoke(gm_client, char["id"], idx, _ACTION_KEYS[slug])
    assert first.status_code == 200, first.text

    second = await _invoke(gm_client, char["id"], idx, _ACTION_KEYS[slug])
    assert second.status_code == 409, second.text
    body = second.json()
    assert body["error"] == "insufficient_charges"
    assert body["current"] == 0
    assert body["requested"] == 1


async def test_long_rest_restores_charge(
    gm_client, roster, fresh_resources,
):
    """v2.403.0 rest flow. Spend → 0; long rest → full restoration.
    Confirms the standard rest-refill path picks up the new resource
    row."""
    carrier_name, slug, _, initial = _BATCH[2]  # Seraphine's censer
    char = roster[carrier_name]

    sheet = await _sheet(gm_client, char["id"])
    idx = _slug_index(sheet.get("inventory") or [], slug)
    first = await _invoke(gm_client, char["id"], idx, _ACTION_KEYS[slug])
    assert first.status_code == 200, first.text
    sheet_after = await _sheet(gm_client, char["id"])
    assert _resource_current(sheet_after, slug) == initial - 1

    rest_resp = await _long_rest(gm_client, char["id"])
    assert rest_resp.status_code == 200, rest_resp.text
    sheet_rested = await _sheet(gm_client, char["id"])
    assert _resource_current(sheet_rested, slug) == initial


async def test_unknown_action_key_returns_404(gm_client, roster):
    """v2.403.0 error path. action_key that doesn't match the catalog →
    404 with the unknown-action message."""
    carrier_name, slug, _, _ = _BATCH[0]
    char = roster[carrier_name]
    sheet = await _sheet(gm_client, char["id"])
    idx = _slug_index(sheet.get("inventory") or [], slug)
    resp = await _invoke(gm_client, char["id"], idx, "not-a-real-key")
    assert resp.status_code == 404, resp.text


async def test_bag_of_tricks_multi_pull_pool(
    gm_client, roster, fresh_resources,
):
    """v2.403.1: Bag of Tricks (3/dawn) supports three sequential pulls
    before hitting 409. Exercises the multi-charge pool variant of the
    shared handler (the 4× 1/dawn elemental items + cape/iron-bands/
    efreeti only support one invocation per rest)."""
    char = roster["Brakka Wildmane"]
    sheet = await _sheet(gm_client, char["id"])
    idx = _slug_index(sheet.get("inventory") or [], "bag-of-tricks")
    # Three pulls in sequence — each decrements 3 → 2 → 1 → 0.
    expected = [2, 1, 0]
    for want in expected:
        resp = await _invoke(gm_client, char["id"], idx, "pull-creature")
        assert resp.status_code == 200, resp.text
        assert resp.json()["resource"]["current"] == want
    # Fourth pull → 409 with current=0.
    fourth = await _invoke(gm_client, char["id"], idx, "pull-creature")
    assert fourth.status_code == 409, fourth.text
    assert fourth.json()["error"] == "insufficient_charges"
    assert fourth.json()["current"] == 0


async def test_pipes_of_the_sewers_multi_charge_spend(gm_client, roster):
    """v2.403.2: Pipes of the Sewers (3 charges, 1d3/dawn) — RAW lets
    the player spend 1-3 charges per use. Test exercises (a) PATCH
    vault-loot to equipped+attuned, (b) spend 2 charges in one call →
    resource 3 → 1, (c) restore the item to inert state on teardown."""
    char = roster["Brakka Wildmane"]
    await _long_rest(gm_client, char["id"])
    prior = await _patch_inventory_item(
        gm_client, char["id"], "pipes-of-the-sewers",
        equipped=True, attuned=True,
    )
    try:
        sheet = await _sheet(gm_client, char["id"])
        idx = _slug_index(sheet.get("inventory") or [], "pipes-of-the-sewers")
        assert idx >= 0
        # Verify the pool is 3/3 after long rest.
        assert _resource_current(sheet, "pipes-of-the-sewers") == 3

        resp = await _invoke(gm_client, char["id"], idx,
                             "summon-rat-swarm", charges=2)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["charges_spent"] == 2
        assert data["resource"]["current"] == 1

        # Out-of-range charges → 400.
        over = await _invoke(gm_client, char["id"], idx,
                             "summon-rat-swarm", charges=4)
        assert over.status_code == 400, over.text
    finally:
        # Restore the inert vault-loot state.
        await _patch_inventory_item(
            gm_client, char["id"], "pipes-of-the-sewers", **prior,
        )
        await _long_rest(gm_client, char["id"])


async def test_helm_of_teleportation_requires_attunement(gm_client, roster):
    """v2.403.2: Helm of Teleportation requires attunement RAW. With
    the helm equipped but NOT attuned, /use_item_action returns 409
    requires attunement; flipping attuned → 200 + charge decrements."""
    char = roster["Thalindra Moonwhisper"]
    await _long_rest(gm_client, char["id"])
    # First test: equipped but not attuned → 409.
    prior = await _patch_inventory_item(
        gm_client, char["id"], "helm-of-teleportation",
        equipped=True, attuned=False,
    )
    try:
        sheet = await _sheet(gm_client, char["id"])
        idx = _slug_index(sheet.get("inventory") or [], "helm-of-teleportation")
        assert idx >= 0
        un_att = await _invoke(gm_client, char["id"], idx, "cast-teleport")
        assert un_att.status_code == 409, un_att.text
        assert "attunement" in un_att.text.lower()
        # Now flip attuned=True and try again → 200.
        await _patch_inventory_item(
            gm_client, char["id"], "helm-of-teleportation", attuned=True,
        )
        ok = await _invoke(gm_client, char["id"], idx, "cast-teleport")
        assert ok.status_code == 200, ok.text
        assert ok.json()["resource"]["current"] == 2  # 3 → 2
    finally:
        await _patch_inventory_item(
            gm_client, char["id"], "helm-of-teleportation", **prior,
        )
        await _long_rest(gm_client, char["id"])


async def test_cube_of_force_variable_charge_spend(gm_client, roster):
    """v2.403.2: Cube of Force (36 charges, 1d20/dawn) — RAW per-face
    cost is 1/2/3/4/5; v1 ships the generic "expend 1-5" action. Test
    spends 3 then 5, asserts the pool drains 36 → 33 → 28, and that
    a >5 spend returns 400."""
    char = roster["Zara Emberfire"]
    await _long_rest(gm_client, char["id"])
    sheet = await _sheet(gm_client, char["id"])
    idx = _slug_index(sheet.get("inventory") or [], "cube-of-force")
    assert idx >= 0
    assert _resource_current(sheet, "cube-of-force") == 36

    spent3 = await _invoke(gm_client, char["id"], idx,
                            "project-barrier", charges=3)
    assert spent3.status_code == 200, spent3.text
    assert spent3.json()["resource"]["current"] == 33

    spent5 = await _invoke(gm_client, char["id"], idx,
                            "project-barrier", charges=5)
    assert spent5.status_code == 200, spent5.text
    assert spent5.json()["resource"]["current"] == 28

    over = await _invoke(gm_client, char["id"], idx,
                          "project-barrier", charges=6)
    assert over.status_code == 400, over.text

    # Long-rest restores via 1d20 recharge dice — current should
    # rise but is bounded by the random roll. Assert it strictly
    # grows from 28 (not full refill).
    await _long_rest(gm_client, char["id"])
    sheet_after = await _sheet(gm_client, char["id"])
    new_cur = _resource_current(sheet_after, "cube-of-force")
    assert new_cur is not None and new_cur > 28 and new_cur <= 36
