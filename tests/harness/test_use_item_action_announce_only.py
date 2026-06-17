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


async def _invoke(gm_client, char_id, inv_idx, action_key):
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/use_item_action",
        json={"inventory_index": inv_idx, "action_key": action_key},
    )


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
