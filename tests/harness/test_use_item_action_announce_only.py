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


_BATCH = [
    ("Rowan Quickbow", "bowl-of-commanding-water-elementals",
     "Bowl of Commanding Water Elementals"),
    ("Sir Caelan Lightbringer", "brazier-of-commanding-fire-elementals",
     "Brazier of Commanding Fire Elementals"),
    ("Dame Seraphine Vael", "censer-of-controlling-air-elementals",
     "Censer of Controlling Air Elementals"),
    ("Krieger Stonefist", "stone-of-controlling-earth-elementals",
     "Stone of Controlling Earth Elementals"),
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


@pytest_asyncio.fixture
async def fresh_resources(gm_client, roster):
    """Long-rest each carrier so the test starts from a known 1/1 pool
    even if a prior test in the suite spent a charge."""
    for carrier_name, _, _ in _BATCH:
        await _long_rest(gm_client, roster[carrier_name]["id"])
    yield
    for carrier_name, _, _ in _BATCH:
        await _long_rest(gm_client, roster[carrier_name]["id"])


async def test_elemental_summon_decrements_charge(
    gm_client, roster, fresh_resources,
):
    """v2.403.0 happy path. For each of the four elemental items:
    invoke → 200 with charges_spent=1, resource.current=0, item_name
    populated. Asserts the charge actually decrements on the sheet."""
    action_keys = {
        "bowl-of-commanding-water-elementals": "summon-water-elemental",
        "brazier-of-commanding-fire-elementals": "summon-fire-elemental",
        "censer-of-controlling-air-elementals": "summon-air-elemental",
        "stone-of-controlling-earth-elementals": "summon-earth-elemental",
    }
    for carrier_name, slug, item_name in _BATCH:
        char = roster[carrier_name]
        sheet = await _sheet(gm_client, char["id"])
        idx = _slug_index(sheet.get("inventory") or [], slug)
        assert idx >= 0, f"{carrier_name} must carry seeded {slug}"
        assert _resource_current(sheet, slug) == 1, \
            f"{slug} should start at 1/1 for {carrier_name}"

        resp = await _invoke(gm_client, char["id"], idx, action_keys[slug])
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["ok"] is True
        assert data["item_name"] == item_name
        assert data["charges_spent"] == 1
        assert data["resource"]["current"] == 0
        assert data["resource"]["max"] == 1
        assert data["resource"]["key"] == slug

        # And the persisted sheet really shows 0.
        sheet_after = await _sheet(gm_client, char["id"])
        assert _resource_current(sheet_after, slug) == 0


async def test_second_use_same_day_returns_409(
    gm_client, roster, fresh_resources,
):
    """v2.403.0 error path. Invoking a second time before a rest →
    409 insufficient_charges with current=0."""
    # Use just one item to exercise the gate (the handler is shared).
    carrier_name, slug, _ = _BATCH[0]  # Rowan's bowl
    action_key = "summon-water-elemental"
    char = roster[carrier_name]

    sheet = await _sheet(gm_client, char["id"])
    idx = _slug_index(sheet.get("inventory") or [], slug)
    first = await _invoke(gm_client, char["id"], idx, action_key)
    assert first.status_code == 200, first.text

    second = await _invoke(gm_client, char["id"], idx, action_key)
    assert second.status_code == 409, second.text
    body = second.json()
    assert body["error"] == "insufficient_charges"
    assert body["current"] == 0
    assert body["requested"] == 1


async def test_long_rest_restores_charge(
    gm_client, roster, fresh_resources,
):
    """v2.403.0 rest flow. Spend → 0; long rest → 1/1. Confirms the
    standard rest-refill path picks up the new resource row."""
    carrier_name, slug, _ = _BATCH[2]  # Seraphine's censer
    action_key = "summon-air-elemental"
    char = roster[carrier_name]

    sheet = await _sheet(gm_client, char["id"])
    idx = _slug_index(sheet.get("inventory") or [], slug)
    first = await _invoke(gm_client, char["id"], idx, action_key)
    assert first.status_code == 200, first.text
    assert (await _sheet(gm_client, char["id"]))
    sheet_after = await _sheet(gm_client, char["id"])
    assert _resource_current(sheet_after, slug) == 0

    rest_resp = await _long_rest(gm_client, char["id"])
    assert rest_resp.status_code == 200, rest_resp.text
    sheet_rested = await _sheet(gm_client, char["id"])
    assert _resource_current(sheet_rested, slug) == 1


async def test_unknown_action_key_returns_404(gm_client, roster):
    """v2.403.0 error path. action_key that doesn't match the catalog →
    404 with the unknown-action message."""
    carrier_name, slug, _ = _BATCH[0]
    char = roster[carrier_name]
    sheet = await _sheet(gm_client, char["id"])
    idx = _slug_index(sheet.get("inventory") or [], slug)
    resp = await _invoke(gm_client, char["id"], idx, "not-a-real-key")
    assert resp.status_code == 404, resp.text
