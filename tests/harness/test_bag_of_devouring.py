"""Bag of Devouring — catalog-only magic item (RAW DMG p.153, very rare).

Unlike its Phase-3 sibling the Bag of Holding (v2.159.30), the Bag of
Devouring ships **catalog-only**: a descriptive, GM-adjudicated row with
no automation wiring (`passives: []`, `actions: []`). Its RAW curse
mechanics — animal/vegetable matter devoured forever, a 50% chance of
swallowing a creature that reaches in (DC 15 STR to escape), once-daily
extraplanar ejection of stored objects, destruction-on-tear — are
explicitly a v1 NON-GOAL of the magic-items-automation framework (see
`docs/plans/magic-items-automation.md` lines 162-167: cursed/sentient
items don't fit the Phase 1-8 action templates). They stay narration.

The load-bearing contrast pinned here: the carry-weight discount is
driven solely by the per-item `_in_bag_of_holding: True` flag in
`app.content.carry_weight`. A Bag of Devouring grants NO such discount —
matter placed inside is consumed/destroyed, not carried weightlessly —
so an item flagged as being in a Bag of Devouring still counts its full
weight. This test pins that there is no `_in_bag_of_devouring` skip.
"""
import httpx

from app.content.carry_weight import sheet_inventory_weight_lb

from .helpers import BASE_URL


async def test_bag_of_devouring_serves_as_catalog_only_item():
    """The catalog row serves with no automation wiring: empty
    `passives`/`actions`, null charge fields, very-rare, no attunement.
    This pins the v1-non-goal decision — the cursed mechanics stay
    GM-adjudicated rather than mapping to an action template."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/api/content/items/bag-of-devouring")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "local-srd"
    record = body["record"]
    assert record["slug"] == "bag-of-devouring"
    assert record["name"] == "Bag of Devouring"
    assert record["rarity"] == "very rare"
    assert record["attunement"] is False
    # Catalog-only: no mechanical wiring of any kind.
    assert record["charges"] is None
    assert record["charge_recovery"] is None
    assert record["passives"] == []
    assert record["actions"] == []


def test_bag_of_devouring_grants_no_carry_discount():
    """Contrast with Bag of Holding: only `_in_bag_of_holding` skips an
    item's weight. An item flagged as being in a Bag of Devouring (or
    any other flag) still counts its full weight against carry capacity.
    A Bag of Devouring consumes/destroys what's placed in it — it does
    not carry it weightlessly."""
    sheet = {
        "abilities": {"STR": 15},
        "inventory": [
            {"name": "Greataxe", "weight_lb": 7, "qty": 1},
            # Flagged as being inside a Bag of Devouring — there is no
            # such skip, so this 59 lb still counts in full.
            {
                "name": "Explorer's pack",
                "weight_lb": 59,
                "qty": 1,
                "_in_bag_of_devouring": True,
            },
        ],
    }
    weight = sheet_inventory_weight_lb(sheet)
    assert weight == 66, (
        f"expected 7 + 59 = 66 lb (no Bag-of-Devouring discount); "
        f"got {weight} lb — a spurious _in_bag_of_devouring skip may "
        f"have leaked into sheet_inventory_weight_lb"
    )

    # Sanity-pin the contrast: the SAME item under the Bag of HOLDING
    # flag IS discounted, proving the skip is holding-specific.
    sheet["inventory"][1] = {
        "name": "Explorer's pack",
        "weight_lb": 59,
        "qty": 1,
        "_in_bag_of_holding": True,
    }
    discounted = sheet_inventory_weight_lb(sheet)
    assert discounted == 7, (
        f"expected the Bag-of-Holding flag to discount the pack "
        f"(7 lb only); got {discounted} lb"
    )
