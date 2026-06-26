"""v2.159.27 — carrying-capacity Phase 1 pure-Python unit tests.

Tests against the leaf module `app.content.carry_weight`. Pure-Python;
no HTTP / WS harness fixtures. RAW PHB p.176: carrying capacity =
STR × 15 lb. See `docs/plans/carrying-capacity.md` for the design.
"""
from app.content.carry_weight import (
    BAG_OF_HOLDING_CAPACITY_LB,
    item_weight_lb,
    parse_weight_lb,
    sheet_bag_of_holding_weight_lb,
    sheet_carry_capacity_lb,
    sheet_carry_summary,
    sheet_inventory_weight_lb,
    sheet_is_over_capacity,
)


# ── parse_weight_lb ──────────────────────────────────────────────────────────


def test_parse_weight_empty_string():
    assert parse_weight_lb("") == 0.0


def test_parse_weight_none():
    assert parse_weight_lb(None) == 0.0


def test_parse_weight_simple_integer():
    assert parse_weight_lb("3 lb.") == 3.0


def test_parse_weight_srd_typo_double_lb():
    """The SRD has a known typo on several items: ``"3 lb. lb"`` —
    the parser pulls the leading numeric and ignores the rest, so the
    typo doesn't matter."""
    assert parse_weight_lb("3 lb. lb") == 3.0


def test_parse_weight_fifteen():
    assert parse_weight_lb("15 lb.") == 15.0


def test_parse_weight_half_lb_fraction():
    assert parse_weight_lb("1/2 lb.") == 0.5


def test_parse_weight_quarter_lb_fraction():
    assert parse_weight_lb("1/4 lb.") == 0.25


def test_parse_weight_decimal():
    assert parse_weight_lb("2.5 lb.") == 2.5


def test_parse_weight_negative_clamped_to_zero():
    """RAW item weights are never negative. Defensive against bad
    homebrew data."""
    assert parse_weight_lb("-5 lb.") == 0.0


def test_parse_weight_unparsable_junk():
    assert parse_weight_lb("unparsable junk text") == 0.0


def test_parse_weight_non_string_defensive():
    """A dict / list / int passed in defensively returns 0."""
    assert parse_weight_lb(123) == 0.0  # type: ignore[arg-type]
    assert parse_weight_lb([]) == 0.0  # type: ignore[arg-type]
    assert parse_weight_lb({}) == 0.0  # type: ignore[arg-type]


# ── item_weight_lb 3-tier priority ───────────────────────────────────────────


def test_item_weight_lb_tier1_direct_override():
    """Tier 1: ``weight_lb`` field on the inventory item wins over
    everything else."""
    item = {"name": "Custom", "weight_lb": 12, "weight": "3 lb."}
    assert item_weight_lb(item, fallback_catalog_weight="99 lb.") == 12.0


def test_item_weight_lb_tier2_item_weight_string():
    """Tier 2: parsed from the item's ``weight`` string."""
    item = {"name": "Custom", "weight": "3 lb."}
    assert item_weight_lb(item, fallback_catalog_weight="99 lb.") == 3.0


def test_item_weight_lb_tier3_catalog_fallback():
    """Tier 3: catalog weight (passed as ``fallback_catalog_weight``)
    is used only when the item has no inline weight."""
    item = {"name": "Custom"}
    assert item_weight_lb(item, fallback_catalog_weight="7 lb.") == 7.0


def test_item_weight_lb_default_zero():
    """All three tiers absent → 0.0."""
    item = {"name": "Custom"}
    assert item_weight_lb(item) == 0.0


def test_item_weight_lb_non_dict_defensive():
    assert item_weight_lb(None) == 0.0  # type: ignore[arg-type]
    assert item_weight_lb("not a dict") == 0.0  # type: ignore[arg-type]


# ── sheet_carry_capacity_lb ──────────────────────────────────────────────────


def test_carry_capacity_str_10_default():
    assert sheet_carry_capacity_lb({"abilities": {"strength": 10}}) == 150


def test_carry_capacity_str_16():
    assert sheet_carry_capacity_lb({"abilities": {"strength": 16}}) == 240


def test_carry_capacity_str_20_caps():
    assert sheet_carry_capacity_lb({"abilities": {"strength": 20}}) == 300


def test_carry_capacity_clamps_below_1():
    """Defensive: STR 0 / negative scores clamp to 1 (min)."""
    assert sheet_carry_capacity_lb({"abilities": {"strength": 0}}) == 15
    assert sheet_carry_capacity_lb({"abilities": {"strength": -5}}) == 15


def test_carry_capacity_missing_abilities_default_10():
    """No abilities field → STR 10 default."""
    assert sheet_carry_capacity_lb({}) == 150


def test_carry_capacity_nested_score_field():
    """Some sheets nest the STR score: ``{"score": 14, "mod": 2}``."""
    assert sheet_carry_capacity_lb({
        "abilities": {"strength": {"score": 14, "mod": 2}},
    }) == 210


def test_carry_capacity_flat_str_field():
    """Some sheets use a flat ``sheet.str`` field."""
    assert sheet_carry_capacity_lb({"str": 18}) == 270


def test_carry_capacity_uppercase_str_key():
    """The dnd5e demo seed uses the uppercase 3-letter key shape
    ``{"abilities": {"STR": 18, "DEX": 14, ...}}``. The helper must
    find STR here too."""
    assert sheet_carry_capacity_lb({
        "abilities": {"STR": 18, "DEX": 14, "CON": 16},
    }) == 270


# ── sheet_inventory_weight_lb ────────────────────────────────────────────────


def test_inventory_weight_empty():
    assert sheet_inventory_weight_lb({"inventory": []}) == 0.0


def test_inventory_weight_single_item():
    assert sheet_inventory_weight_lb({
        "inventory": [{"name": "Longsword", "weight_lb": 3, "qty": 1}],
    }) == 3.0


def test_inventory_weight_qty_multiplies():
    assert sheet_inventory_weight_lb({
        "inventory": [{"name": "Dagger", "weight_lb": 1, "qty": 2}],
    }) == 2.0


def test_inventory_weight_qty_default_one():
    """Missing qty defaults to 1."""
    assert sheet_inventory_weight_lb({
        "inventory": [{"name": "X", "weight_lb": 5}],
    }) == 5.0


def test_inventory_weight_sum_across_items():
    assert sheet_inventory_weight_lb({
        "inventory": [
            {"name": "Longsword", "weight_lb": 3, "qty": 1},
            {"name": "Plate Armor", "weight_lb": 65, "qty": 1},
            {"name": "Dagger", "weight_lb": 1, "qty": 2},
        ],
    }) == 70.0


def test_inventory_weight_catalog_fallback():
    """Items without inline weights fall back to catalog strings."""
    catalog = {"longsword": "3 lb.", "rations": "2 lb."}
    sheet = {
        "inventory": [
            {"name": "Longsword", "_slug": "longsword", "qty": 1},
            {"name": "Rations", "_slug": "rations", "qty": 5},
        ],
    }
    assert sheet_inventory_weight_lb(sheet, catalog) == 13.0  # 3 + (2*5)


def test_inventory_weight_skips_in_bag_of_holding():
    """v2.159.27 Phase 3 hook landed early: items flagged
    `_in_bag_of_holding: True` are excluded from the weight sum.
    The Bag itself stays."""
    sheet = {
        "inventory": [
            {"name": "Bag of Holding", "weight_lb": 15, "qty": 1,
             "_slug": "bag-of-holding"},
            {"name": "Plate Armor", "weight_lb": 65, "qty": 1,
             "_in_bag_of_holding": True},
            {"name": "Anvil", "weight_lb": 200, "qty": 1,
             "_in_bag_of_holding": True},
        ],
    }
    # Only the Bag's own 15 lb should count.
    assert sheet_inventory_weight_lb(sheet) == 15.0


# ── sheet_is_over_capacity ───────────────────────────────────────────────────


def test_is_over_capacity_under():
    sheet = {
        "abilities": {"strength": 14},  # 210 lb cap
        "inventory": [{"name": "Stuff", "weight_lb": 100, "qty": 1}],
    }
    assert sheet_is_over_capacity(sheet) is False


def test_is_over_capacity_over():
    sheet = {
        "abilities": {"strength": 10},  # 150 lb cap
        "inventory": [{"name": "Big Stuff", "weight_lb": 200, "qty": 1}],
    }
    assert sheet_is_over_capacity(sheet) is True


def test_is_over_capacity_exactly_at_cap_is_not_over():
    """Exact cap is NOT over. RAW: "you can carry up to" means
    inclusive."""
    sheet = {
        "abilities": {"strength": 10},  # 150 lb cap
        "inventory": [{"name": "X", "weight_lb": 150, "qty": 1}],
    }
    assert sheet_is_over_capacity(sheet) is False


# ── sheet_carry_summary ──────────────────────────────────────────────────────


def test_carry_summary_bundles_three_fields():
    summary = sheet_carry_summary({
        "abilities": {"strength": 16},  # 240 lb cap
        "inventory": [
            {"name": "Longsword", "weight_lb": 3, "qty": 1},
            {"name": "Plate Armor", "weight_lb": 65, "qty": 1},
        ],
    })
    assert summary == {
        "carry_capacity_lb": 240,
        "inventory_weight_lb": 68.0,
        "is_over_capacity": False,
    }


def test_carry_summary_over_capacity_flag():
    summary = sheet_carry_summary({
        "abilities": {"strength": 8},  # 120 lb cap
        "inventory": [{"name": "Heavy", "weight_lb": 200, "qty": 1}],
    })
    assert summary["is_over_capacity"] is True
    assert summary["inventory_weight_lb"] == 200.0
    assert summary["carry_capacity_lb"] == 120


# ── Integration: /sheet-json populates derived.carry ────────────────────────


import httpx
import pytest

BASE_URL = "http://localhost:8013"


@pytest.mark.asyncio
async def test_sheet_json_exposes_derived_carry(gm_client):
    """v2.159.27 — /sheet-json now bundles a `derived.carry` summary
    for D&D 5e PCs. Asserts the three fields are present and shaped
    correctly for one demo PC (Krieger — Barbarian, high STR).
    """
    from .conftest import CAMPAIGN_ID  # noqa: I001
    roster_resp = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/roster")
    chars = roster_resp.json().get("characters") or []
    krieger = next(c for c in chars if c["name"] == "Krieger Stonefist")
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    derived = data.get("derived") or {}
    carry = derived.get("carry") or {}
    assert "carry_capacity_lb" in carry
    assert "inventory_weight_lb" in carry
    assert "is_over_capacity" in carry
    cap = int(carry["carry_capacity_lb"])
    assert cap > 0, f"expected positive carry capacity, got {cap}"
    # Krieger is a Barbarian — STR should be high (16+), so capacity
    # at least 240 lb.
    assert cap >= 240, (
        f"Barbarian carry capacity should be ≥ 240 lb (STR 16+); got {cap}"
    )


# ── Bag of Holding 500-lb capacity (v2.656.0) ────────────────────────────────


def test_bag_weight_sums_only_in_bag_items():
    sheet = {"inventory": [
        {"name": "Greataxe", "weight_lb": 7},                       # on-person
        {"name": "Anvil", "weight_lb": 200, "_in_bag_of_holding": True},
        {"name": "Crates", "weight_lb": 100, "qty": 2, "_in_bag_of_holding": True},
    ]}
    # On-person sum excludes the bagged items.
    assert sheet_inventory_weight_lb(sheet) == 7
    # Bag sum is only the bagged items: 200 + 100×2 = 400.
    assert sheet_bag_of_holding_weight_lb(sheet) == 400


def test_bag_weight_zero_when_nothing_stowed():
    sheet = {"inventory": [{"name": "Greataxe", "weight_lb": 7}]}
    assert sheet_bag_of_holding_weight_lb(sheet) == 0.0


def test_summary_omits_bag_fields_without_a_bag():
    sheet = {"abilities": {"STR": 14},
             "inventory": [{"name": "Greataxe", "weight_lb": 7}]}
    s = sheet_carry_summary(sheet)
    assert "bag_of_holding_weight_lb" not in s
    assert "bag_of_holding_over_capacity" not in s


def test_summary_flags_bag_under_capacity():
    sheet = {"abilities": {"STR": 14}, "inventory": [
        {"name": "Pack", "weight_lb": 59, "_in_bag_of_holding": True},
    ]}
    s = sheet_carry_summary(sheet)
    assert s["bag_of_holding_weight_lb"] == 59
    assert s["bag_of_holding_capacity_lb"] == BAG_OF_HOLDING_CAPACITY_LB == 500
    assert s["bag_of_holding_over_capacity"] is False


def test_summary_flags_bag_rupture_over_500():
    sheet = {"abilities": {"STR": 20}, "inventory": [
        {"name": "Gold bars", "weight_lb": 501, "_in_bag_of_holding": True},
    ]}
    s = sheet_carry_summary(sheet)
    assert s["bag_of_holding_weight_lb"] == 501
    assert s["bag_of_holding_over_capacity"] is True
    # The bagged weight still doesn't burden the wielder (0 on-person).
    assert s["inventory_weight_lb"] == 0
