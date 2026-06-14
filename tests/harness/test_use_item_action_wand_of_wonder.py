"""v2.273.0 — charged-items Phase 4: Wand of Wonder (RAW DMG p.213, rare,
attunement by a spellcaster): 7 charges (regain 1d6+1 at dawn). The first
``action_kind: "random_table"`` charge action — spend 1 charge and roll
d100 on the Wand of Wonder chaos table; the rolled row names the effect
for the GM to narrate/resolve.

  - the handler decrements 1 charge and rolls d100 (or honors a
    ``force_roll`` 1-100 override for deterministic tests / GM choice),
  - the response carries ``action_kind: "random_table"``, the ``roll``,
    the ``row_key`` / ``effect`` / ``description``, and the resource pool,
  - per-row sub-effects (fireball, lightning bolt, petrification…) are
    GM-adjudicated in v1.

Demo fixture: Zara (Tiefling Draconic Sorcerer) carries an equipped +
attuned Wand of Wonder + a 7-charge resource row at key ``wand-of-wonder``.

Tests:
  - happy path: roll with no params → action_kind random_table, roll in
    1..100, charges_spent=1, resource 7 → 6
  - force_roll=72 → the fireball row (70-79 band) resolves deterministically
  - empty wand (drained to 0) → 409 insufficient_charges
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_SLUG = "wand-of-wonder"


async def _wand_inv_idx(gm_client, char_id):
    sheet_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    sheet = sheet_resp.json().get("sheet") or {}
    inv = sheet.get("inventory") or []
    for i, it in enumerate(inv):
        if isinstance(it, dict) and it.get("_slug") == _SLUG:
            return i
    raise AssertionError("Zara has no wand-of-wonder item")


@pytest_asyncio.fixture
async def zara(roster):
    return roster["Zara Emberfire"]


@pytest_asyncio.fixture
async def zara_full_wand(gm_client, zara):
    """Force-reseed Zara's Wand of Wonder to a full 7 charges, restoring
    the snapshot on teardown."""
    sheet_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/sheet-json",
    )
    sheet = sheet_resp.json().get("sheet") or {}
    resources = list(sheet.get("resources") or [])
    snapshot = [dict(r) if isinstance(r, dict) else r for r in resources]
    for i, r in enumerate(resources):
        if isinstance(r, dict) and r.get("key") == _SLUG:
            resources[i] = {**r, "current": 7, "max": 7}
            break
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/sheet-fields",
        json={"resources": resources},
    )
    yield zara
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/sheet-fields",
        json={"resources": snapshot},
    )


async def test_wand_of_wonder_roll_happy_path(gm_client, zara_full_wand):
    """Happy path: unleash wonder with no params → action_kind
    random_table, roll in 1..100, charges 7 → 6, a non-empty effect."""
    zara = zara_full_wand
    idx = await _wand_inv_idx(gm_client, zara["id"])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/use_item_action",
        json={"inventory_index": idx, "action_key": "wonder"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["action_kind"] == "random_table"
    assert 1 <= data["roll"] <= 100
    assert data["charges_spent"] == 1
    assert data["resource"]["current"] == 6  # 7 → 6
    assert data["effect"]
    assert data["row_key"]


async def test_wand_of_wonder_force_roll_fireball(gm_client, zara_full_wand):
    """force_roll=72 lands in the 70-79 band → the fireball row resolves
    deterministically."""
    zara = zara_full_wand
    idx = await _wand_inv_idx(gm_client, zara["id"])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/use_item_action",
        json={"inventory_index": idx, "action_key": "wonder", "force_roll": 72},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["roll"] == 72
    assert data["row_key"] == "fireball"
    assert "Fireball" in data["effect"]
    assert data["resource"]["current"] == 6


async def test_wand_of_wonder_empty_returns_409(gm_client, zara):
    """Drain the wand to 0 via /sheet-fields, then try to roll → 409
    insufficient_charges."""
    sheet_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/sheet-json",
    )
    sheet = sheet_resp.json().get("sheet") or {}
    resources = list(sheet.get("resources") or [])
    snapshot = [dict(r) if isinstance(r, dict) else r for r in resources]
    drained = [
        {**r, "current": 0} if (isinstance(r, dict) and r.get("key") == _SLUG) else r
        for r in resources
    ]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/sheet-fields",
        json={"resources": drained},
    )
    try:
        idx = await _wand_inv_idx(gm_client, zara["id"])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/use_item_action",
            json={"inventory_index": idx, "action_key": "wonder"},
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
