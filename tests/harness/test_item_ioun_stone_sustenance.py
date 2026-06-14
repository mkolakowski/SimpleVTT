"""v2.230.0 — Ioun Stone of Sustenance (RAW DMG p.176, rare, attunement):
the third non-ability Ioun variant on the shared `ioun-stone` slug, and the
first to surface a sustenance passive.

RAW: a clear spindle that orbits your head; while it does, you don't need to
eat or drink. The flag rides the inventory item via `_no_food_or_drink: True`
(no ability payload), aggregates in `_equipped_item_effects` (boolean OR into
`no_food_or_drink`), and surfaces on `/sheet-json` as
`derived.no_food_or_drink = {sources}`.

Demo fixture: Rowan Quickbow (Ranger) wears an equipped + attuned Ioun Stone
of Sustenance. v2.247.0 detuned his Ioun Stone of Charisma (kept equipped) to
free a slot for the Boots of the Winterlands, so the coexistence test now
proves the no-eat/drink flag composes with the STR override from his still-
attuned Gauntlets of Ogre Power — distinct per-item riders surfacing together
in `derived`.
"""
from .conftest import CAMPAIGN_ID

_IOUN_SLUG = "ioun-stone"


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_sustenance_exposes_no_food_or_drink_on_sheet_json(gm_client, roster):
    """Happy path: Rowan's `/sheet-json` reports `derived.no_food_or_drink`
    with the stone named in its sources."""
    rowan = roster["Rowan Quickbow"]
    data = await _sheet_json(gm_client, rowan["id"])
    sustenance = (data.get("derived") or {}).get("no_food_or_drink")
    assert sustenance is not None, (
        f"expected derived.no_food_or_drink, got: {data.get('derived')!r}"
    )
    assert any(
        "Ioun Stone of Sustenance" in str(s)
        for s in sustenance.get("sources") or []
    ), f"expected the stone named in sources, got: {sustenance!r}"


async def test_sustenance_coexists_with_gauntlets_str(gm_client, roster):
    """Rowan's distinct equipped items compose in `derived`: the Sustenance
    ioun stone sets the no-eat/drink flag while his Gauntlets of Ogre Power
    still set STR to 19 — proving per-item riders surface together without
    interfering. (Before v2.247.0 this paired with the Ioun Stone of
    Charisma; that stone is now detuned to free a slot for the Boots of the
    Winterlands, so the STR override stands in.)"""
    rowan = roster["Rowan Quickbow"]
    data = await _sheet_json(gm_client, rowan["id"])
    derived = data.get("derived") or {}
    assert derived.get("no_food_or_drink") is not None, derived
    eff = derived.get("effective_abilities") or {}
    assert "STR" in eff, f"expected STR override from the gauntlets, got {eff!r}"
    assert eff["STR"]["effective"] == 19, eff["STR"]


async def test_sustenance_unequip_drops_flag(gm_client, roster):
    """Unequipping the Sustenance stone removes `derived.no_food_or_drink`.
    Restores the original inventory on teardown."""
    rowan = roster["Rowan Quickbow"]
    data = await _sheet_json(gm_client, rowan["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    idx = next(
        (i for i, it in enumerate(inv)
         if isinstance(it, dict)
         and it.get("_slug") == _IOUN_SLUG
         and it.get("_no_food_or_drink")),
        None,
    )
    assert idx is not None, "Rowan has no Ioun Stone of Sustenance item"
    try:
        inv[idx] = {**inv[idx], "equipped": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/sheet-fields",
            json={"inventory": inv},
        )
        data2 = await _sheet_json(gm_client, rowan["id"])
        assert "no_food_or_drink" not in (data2.get("derived") or {}), (
            f"expected no no_food_or_drink after unequip, got: {data2.get('derived')!r}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/sheet-fields",
            json={"inventory": snapshot},
        )
