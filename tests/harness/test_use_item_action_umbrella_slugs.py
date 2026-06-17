"""v2.404.0 — magic-items-automation Phase 9.3 umbrella-slug closure.

Real mechanical wiring for the four umbrella SRD slugs that closed
the audit denominator from 235/239 to 239/239:

  - `potion-of-healing` — real self-heal handler (2d4+2 basic; tier
    picker via `_tier` for 4d4+4 / 8d4+8 / 10d4+20 variants).
  - `spell-scroll` — real cast-from-scroll handler (spell from
    `_spell_slug` field; consumed on use).
  - `weapon-1-2-or-3` — catalog-stub passive (+N rides per-instance).
  - `wand-of-the-war-mage-1-2-or-3` — catalog-stub passive mirroring
    the existing `wand-of-the-war-mage` row.

These tests cover the two real handlers; the two catalog stubs are
covered by the audit-registry inspection elsewhere.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


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


async def _invoke(gm_client, char_id, inv_idx, action_key):
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/use_item_action",
        json={"inventory_index": inv_idx, "action_key": action_key},
    )


# ─────────────────────────────────────────────────────────────────────
# Potion of Healing
# ─────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def thalindra(roster):
    return roster["Thalindra Moonwhisper"]


@pytest_asyncio.fixture
async def pip(roster):
    return roster["Pip Quickfingers"]


async def test_potion_of_healing_drink_basic_tier(gm_client, pip):
    """v2.404.0 happy path: drink a basic Potion of Healing (tier 1,
    2d4+2). HP rises by the rolled total (clamped at max). Inventory
    decrement: the qty=1 entry is removed on drink. Pip Quickfingers
    carries one in the demo seed. Restores state on teardown by
    re-adding the potion + healing back to full."""
    # Snapshot Pip's HP max for the restore step.
    sheet_pre = await _sheet(gm_client, pip["id"])
    hp_max = int((sheet_pre.get("hp") or {}).get("max") or 0)
    assert hp_max > 0

    # Set HP down so the heal has something to do.
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-fields",
        json={"hp": {"current": 5, "max": hp_max, "temp": 0}},
    )
    sheet = await _sheet(gm_client, pip["id"])
    idx = _slug_index(sheet.get("inventory") or [], "potion-of-healing")
    assert idx >= 0, "Pip must carry seeded potion-of-healing"

    try:
        resp = await _invoke(gm_client, pip["id"], idx, "drink")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["ok"] is True
        assert data["tier"] == 1
        assert data["dice_expression"] == "2d4+2"
        # Roll bounded by 2d4+2: min 4, max 10.
        assert 4 <= data["roll"] <= 10
        assert data["hp_before"] == 5
        assert data["hp_after"] == 5 + data["roll"]
        assert data["healed"] == data["roll"]
        assert data["item_name"] == "Potion of Healing"
    finally:
        # Restore Pip: re-add a potion-of-healing + heal back to full.
        sheet_now = await _sheet(gm_client, pip["id"])
        inv = list(sheet_now.get("inventory") or [])
        inv.append({
            "name": "Potion of Healing", "type": "magic", "qty": 1,
            "equippable": True, "equipped": True, "consumable": True,
            "_slug": "potion-of-healing",
            "desc": "Drink to regain 2d4+2 HP.",
        })
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-fields",
            json={
                "inventory": inv,
                "hp": {"current": hp_max, "max": hp_max, "temp": 0},
            },
        )


async def test_potion_of_healing_tier_picker(gm_client, thalindra):
    """v2.404.0: drinking a tier-3 (Superior) potion rolls 8d4+8 dice
    instead of the basic 2d4+2. Tests the `_tier` field on the
    inventory item drives the picker. PATCHes a fresh tier-3 potion in,
    drinks it, asserts dice + heal range."""
    # PATCH HP down + add a tier-3 potion.
    sheet = await _sheet(gm_client, thalindra["id"])
    inv = list(sheet.get("inventory") or [])
    inv.append({
        "name": "Potion of Superior Healing", "type": "magic", "qty": 1,
        "equippable": True, "equipped": True, "consumable": True,
        "_slug": "potion-of-healing",
        "_tier": 3,
        "desc": "Superior tier — 8d4+8 HP on drink.",
    })
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-fields",
        json={
            "inventory": inv,
            "hp": {"current": 1, "max": 38, "temp": 0},
        },
    )
    sheet = await _sheet(gm_client, thalindra["id"])
    inv = sheet.get("inventory") or []
    # Find the tier-3 entry (last potion-of-healing matching _tier=3).
    idx = -1
    for i, it in enumerate(inv):
        if (isinstance(it, dict) and it.get("_slug") == "potion-of-healing"
                and int(it.get("_tier") or 1) == 3):
            idx = i
            break
    assert idx >= 0

    try:
        resp = await _invoke(gm_client, thalindra["id"], idx, "drink")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["tier"] == 3
        assert data["dice_expression"] == "8d4+8"
        # 8d4+8: min 16, max 40. (Heal clamps at 37 since max HP is 38
        # and we started at 1; healed = min(rolled, 37).)
        assert data["roll"] >= 16
        assert data["roll"] <= 40
        assert data["hp_before"] == 1
        assert data["hp_after"] <= 38
        assert data["item_name"] == "Potion of Superior Healing"
    finally:
        # Restore Thalindra to full HP. The tier-3 potion was consumed.
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-fields",
            json={"hp": {"current": 38, "max": 38, "temp": 0}},
        )


# ─────────────────────────────────────────────────────────────────────
# Spell Scroll
# ─────────────────────────────────────────────────────────────────────


async def test_spell_scroll_consumes_on_cast(gm_client, thalindra):
    """v2.404.0: Spell Scroll (Magic Missile) — invoke `/use_item_action`
    with action_key=cast-spell, the scroll is consumed (qty=1 entry
    removed from inventory), response carries the spell label. Restores
    Thalindra's inventory by re-adding the scroll on teardown."""
    sheet = await _sheet(gm_client, thalindra["id"])
    idx = _slug_index(sheet.get("inventory") or [], "spell-scroll")
    assert idx >= 0, "Thalindra must carry seeded spell-scroll"

    try:
        resp = await _invoke(
            gm_client, thalindra["id"], idx, "cast-spell",
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["ok"] is True
        assert data["consumed"] is True
        assert data["spell_slug"] == "magic-missile"
        assert data["spell_label"] == "Magic Missile"

        # Inventory entry should be gone.
        sheet_after = await _sheet(gm_client, thalindra["id"])
        idx_after = _slug_index(
            sheet_after.get("inventory") or [], "spell-scroll",
        )
        assert idx_after < 0, "scroll should be consumed on use"
    finally:
        # Restore the scroll.
        sheet_now = await _sheet(gm_client, thalindra["id"])
        inv = list(sheet_now.get("inventory") or [])
        inv.append({
            "name": "Spell Scroll (Magic Missile)", "type": "magic",
            "qty": 1, "equippable": True, "equipped": True,
            "consumable": True,
            "_slug": "spell-scroll",
            "_spell_slug": "magic-missile",
            "_spell_name": "Magic Missile",
            "desc": "Common consumable. Cast Magic Missile.",
        })
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-fields",
            json={"inventory": inv},
        )
