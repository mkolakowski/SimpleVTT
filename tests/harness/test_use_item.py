"""/api/campaign/{cid}/use_item — consumable item Use endpoint tests.

Phase 1.5 scope: error paths + invariant assertions. A full happy-path
test depends on JSON access to a character's inventory (no /sheet GET
endpoint exists today), so we test:
  - 400 missing fields
  - 404 unknown inventory_index
  - 400 non-consumable inventory_index (Pip's Shortsword at index 0)

Happy-path coverage moves to Phase 2 once /sheet GET (or per-character
inventory snapshot) lands.
"""
from .conftest import CAMPAIGN_ID


async def test_use_item_missing_fields(gm_client):
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_item",
        json={},
    )
    assert resp.status_code == 400


async def test_use_item_unknown_index(gm_client, roster):
    """Out-of-range inventory_index returns 404."""
    pip = roster["Pip Quickfingers"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_item",
        json={
            "character_id": pip["id"],
            "inventory_index": 999,
            "override": True,
        },
    )
    assert resp.status_code == 404


async def test_use_item_non_consumable(gm_client, roster):
    """Pip's first inventory entry is the Shortsword (a weapon, not
    consumable). The endpoint returns 400 'Not a consumable item'."""
    pip = roster["Pip Quickfingers"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_item",
        json={
            "character_id": pip["id"],
            "inventory_index": 0,  # Shortsword in _rogue_sheet
            "override": True,
        },
    )
    assert resp.status_code == 400
    body = resp.json()
    assert "consumable" in body.get("detail", "").lower()
