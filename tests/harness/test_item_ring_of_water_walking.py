"""v2.241.0 — Ring of Water Walking (RAW DMG p.193, uncommon, no attunement):
while worn, you can stand on and move across any liquid surface as if it were
solid ground.

The flag rides the `ring-of-water-walking` catalog payload (`water_walk:
True`), aggregates in `_equipped_item_effects` (boolean OR into a new
`water_walk` field + `water_walk_sources`), and surfaces on `/sheet-json` as
`derived.water_walk = {sources}`. No attunement — it rides alongside a full
3/3 attunement loadout.

Demo fixture: Rowan Quickbow (Ranger) wears it — no attunement, so it rides
alongside his Gauntlets of Ogre Power + two Ioun Stones — fitting for a ranger
crossing rivers and marshes on the hunt.
"""
from .conftest import CAMPAIGN_ID

_RING_SLUG = "ring-of-water-walking"


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_ring_of_water_walking_exposes_flag(gm_client, roster):
    """Happy path: Rowan's `/sheet-json` reports `derived.water_walk` with
    the ring named in its sources."""
    rowan = roster["Rowan Quickbow"]
    data = await _sheet_json(gm_client, rowan["id"])
    ww = (data.get("derived") or {}).get("water_walk")
    assert ww is not None, (
        f"expected derived.water_walk, got: {data.get('derived')!r}"
    )
    assert any(
        "Ring of Water Walking" in str(s) for s in ww.get("sources") or []
    ), f"expected the ring named in sources, got: {ww!r}"


async def test_ring_of_water_walking_no_attunement_required(gm_client, roster):
    """The ring needs no attunement — the flag rides alongside Rowan's full
    3/3 attunement loadout. `derived.no_food_or_drink` (from his Ioun Stone
    of Sustenance) still reports alongside `water_walk` from the same
    walker."""
    rowan = roster["Rowan Quickbow"]
    data = await _sheet_json(gm_client, rowan["id"])
    derived = data.get("derived") or {}
    assert derived.get("water_walk") is not None, derived
    assert derived.get("no_food_or_drink") is not None, (
        f"expected no_food_or_drink to still report alongside water_walk, "
        f"got: {derived!r}"
    )


async def test_ring_of_water_walking_unequip_drops_flag(gm_client, roster):
    """Unequipping the ring removes `derived.water_walk`. Restores the
    original inventory on teardown."""
    rowan = roster["Rowan Quickbow"]
    data = await _sheet_json(gm_client, rowan["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    idx = next(
        (i for i, it in enumerate(inv)
         if isinstance(it, dict) and it.get("_slug") == _RING_SLUG),
        None,
    )
    assert idx is not None, "Rowan has no Ring of Water Walking item"
    try:
        inv[idx] = {**inv[idx], "equipped": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/sheet-fields",
            json={"inventory": inv},
        )
        data2 = await _sheet_json(gm_client, rowan["id"])
        assert "water_walk" not in (data2.get("derived") or {}), (
            f"expected no water_walk after unequip, got: "
            f"{data2.get('derived')!r}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/sheet-fields",
            json={"inventory": snapshot},
        )
