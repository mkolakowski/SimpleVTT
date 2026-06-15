"""v2.327.0 — "The Wayfarer's Trio" bundle: three SRD wondrous items shipped
as pure catalog-stub passives in `_MAGIC_ITEM_PASSIVES`. Each has GM-narrated
mechanics (no save, damage, or buff to wire); the catalog row exists so the
slug counts in the SRD audit and so future mechanical extensions have a
home. Seeded on thematic carriers:

  - Folding Boat (RAW DMG p.170, rare, no attunement) → Garrik (Fighter,
    Soldier background — emergency river-crossing kit).
  - Rope of Climbing (RAW DMG p.197, uncommon, no attunement) → Pip
    (Halfling Rogue — climbing + stealth toolkit).
  - Bag of Devouring (RAW DMG p.153, very rare, no attunement) → Krieger
    (Half-Orc Barbarian — cursed horror-bag fits the rage aesthetic).

The smoke tests verify each item is reachable on the carrier's
`/sheet-json` inventory by its `_slug` — proves the seed loaded and the
data layer surfaces the items. Any future mechanical extension lands its
own dedicated test file.
"""
from .conftest import CAMPAIGN_ID


async def _carrier_inv(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return list((resp.json().get("sheet") or {}).get("inventory") or [])


def _find_by_slug(inv, slug):
    for it in inv:
        if isinstance(it, dict) and it.get("_slug") == slug:
            return it
    return None


async def test_garrik_carries_folding_boat(gm_client, roster):
    """Folding Boat is seeded on Garrik Ironside (Fighter) at the inventory
    tail — equipped=False (it's stowed), no attunement."""
    garrik = roster["Garrik Ironside"]
    inv = await _carrier_inv(gm_client, garrik["id"])
    boat = _find_by_slug(inv, "folding-boat")
    assert boat is not None, (
        f"Garrik should carry a Folding Boat; got slugs="
        f"{[(it.get('_slug') if isinstance(it, dict) else None) for it in inv]}"
    )
    assert boat.get("name") == "Folding Boat"
    assert boat.get("type") == "magic"
    assert not boat.get("attuned"), (
        f"Folding Boat is no-attunement (RAW); got: {boat!r}"
    )


async def test_pip_carries_rope_of_climbing(gm_client, roster):
    """Rope of Climbing is seeded on Pip Quickfingers (Rogue) at the
    inventory tail — equipped=True (kept ready), no attunement."""
    pip = roster["Pip Quickfingers"]
    inv = await _carrier_inv(gm_client, pip["id"])
    rope = _find_by_slug(inv, "rope-of-climbing")
    assert rope is not None, (
        f"Pip should carry a Rope of Climbing; got slugs="
        f"{[(it.get('_slug') if isinstance(it, dict) else None) for it in inv]}"
    )
    assert rope.get("name") == "Rope of Climbing"
    assert rope.get("type") == "magic"
    assert rope.get("equipped") is True
    assert not rope.get("attuned"), (
        f"Rope of Climbing is no-attunement (RAW); got: {rope!r}"
    )


async def test_krieger_carries_bag_of_devouring(gm_client, roster):
    """Bag of Devouring is seeded on Krieger Stonefist (Barbarian) at the
    inventory tail — equipped=True (cursed item the GM can swap to a
    Bag-of-Holding mishap), no attunement (RAW)."""
    krieger = roster["Krieger Stonefist"]
    inv = await _carrier_inv(gm_client, krieger["id"])
    bag = _find_by_slug(inv, "bag-of-devouring")
    assert bag is not None, (
        f"Krieger should carry a Bag of Devouring; got slugs="
        f"{[(it.get('_slug') if isinstance(it, dict) else None) for it in inv]}"
    )
    assert bag.get("name") == "Bag of Devouring"
    assert bag.get("type") == "magic"
    assert not bag.get("attuned"), (
        f"Bag of Devouring is no-attunement (RAW); got: {bag!r}"
    )
