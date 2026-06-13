"""v2.230.0 — Ioun Stone of Sustenance (RAW DMG p.176, rare, attunement):
the third non-ability Ioun variant on the shared `ioun-stone` slug, and the
first to surface a sustenance passive.

RAW: a clear spindle that orbits your head; while it does, you don't need to
eat or drink. The flag rides the inventory item via `_no_food_or_drink: True`
(no ability payload), aggregates in `_equipped_item_effects` (boolean OR into
`no_food_or_drink`), and surfaces on `/sheet-json` as
`derived.no_food_or_drink = {sources}`.

Demo fixture: Rowan Quickbow (Ranger) wears an equipped + attuned Ioun Stone
of Sustenance — his 3rd attuned item (after the Gauntlets of Ogre Power + Ioun
Stone of Charisma, RAW max 3) and his second ioun stone, so the no-eat/drink
flag and the CHA bonus compose on the one slug via distinct per-item riders.
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


async def test_sustenance_coexists_with_charisma_ioun(gm_client, roster):
    """Rowan's two ioun stones compose: the Sustenance stone sets the no-
    eat/drink flag while the Charisma stone still raises CHA (8 → 10),
    proving distinct per-item riders share the one slug without
    interfering."""
    rowan = roster["Rowan Quickbow"]
    data = await _sheet_json(gm_client, rowan["id"])
    derived = data.get("derived") or {}
    assert derived.get("no_food_or_drink") is not None, derived
    eff = derived.get("effective_abilities") or {}
    assert "CHA" in eff, f"expected CHA override from the second stone, got {eff!r}"
    assert eff["CHA"]["base"] == 8 and eff["CHA"]["effective"] == 10, eff["CHA"]


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
