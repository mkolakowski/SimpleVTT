"""v2.159.30 — carrying-capacity Phase 3 (CLOSES the plan): Bag of
Holding catalog row + demo fixture.

RAW DMG p.153 (uncommon, no attunement): the bag itself weighs 15 lb
regardless of contents; items "inside" don't count against the
wielder's carry capacity. The v2.159.27 leaf module's
`sheet_inventory_weight_lb` already skips items flagged
`_in_bag_of_holding: True` — this commit ships the catalog row,
demo seed, and the integration test that exercises the discount.

Brakka Wildmane (Barbarian Path of the Beast Lv 5) carries:
  - Greataxe 7 lb (equipped, NOT in bag)
  - 4 Javelins × 2 lb = 8 lb (equipped, NOT in bag — RAW: ready)
  - Explorer's pack 59 lb (tagged `_in_bag_of_holding: True`)
  - Bag of Holding 15 lb (the bag itself)

Without the discount: 7 + 8 + 59 + 15 = 89 lb.
With the discount:    7 + 8 + 15      = 30 lb (59 lb saved).

Brakka's base STR 17, but her Storm Belt of Giant Strength sets
effective STR 29 → 435 lb cap. Either way she's well under; the
delta is the test.
"""
import pytest

from .conftest import CAMPAIGN_ID


@pytest.mark.asyncio
async def test_brakka_bag_of_holding_discounts_pack_weight(gm_client):
    """v2.159.30: Brakka's /sheet-json carry summary shows
    `inventory_weight_lb` reflecting the Bag-of-Holding discount.
    Without the discount the sum would be 89 lb; with it the sum is
    30 lb. The 59 lb delta == Explorer's pack weight."""
    roster_resp = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/roster")
    chars = roster_resp.json().get("characters") or []
    brakka = next(c for c in chars if c["name"] == "Brakka Wildmane")
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{brakka['id']}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    carry = (data.get("derived") or {}).get("carry") or {}
    weight = float(carry.get("inventory_weight_lb") or 0)
    # Expected: 7 (greataxe) + 8 (4 javelins × 2) + 15 (bag itself) = 30.
    # Explorer's pack (59 lb) is excluded by the _in_bag_of_holding flag.
    assert weight == 30, (
        f"expected Brakka's bag-discounted inventory = 30 lb; "
        f"got {weight} lb (Bag of Holding skip may have regressed)"
    )
    cap = int(carry.get("carry_capacity_lb") or 0)
    # Brakka base STR 17, but her equipped+attuned Belt of Giant Strength
    # (Storm, v2.223.0) sets effective STR to 29 → 29 × 15 = 435 lb cap.
    assert cap == 435, f"expected cap 435 (effective STR 29 × 15); got {cap}"
    assert carry.get("is_over_capacity") is False
