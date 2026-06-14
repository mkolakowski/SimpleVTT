"""v2.256.0 — Cap of Water Breathing (RAW DMG p.157, uncommon, no
attunement): while worn, you can breathe normally underwater.

The flag rides the `cap-of-water-breathing` catalog payload (`water_breath:
True`), aggregates in `_equipped_item_effects` (boolean OR into a new
`water_breath` field + `water_breath_sources`), and surfaces on `/sheet-json`
as `derived.water_breath = {sources}`. No attunement — it rides alongside the
wearer's loadout freely (the Ring of Water Walking pattern).

Demo fixture: Mira Greenleaf (Druid) wears it — pairs with her Ring of
Swimming, so she can both swim AND breathe underwater.
"""
from .conftest import CAMPAIGN_ID

_CAP_SLUG = "cap-of-water-breathing"


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_cap_of_water_breathing_exposes_flag(gm_client, roster):
    """Happy path: Mira's `/sheet-json` reports `derived.water_breath` with
    the cap named in its sources."""
    mira = roster["Mira Greenleaf"]
    data = await _sheet_json(gm_client, mira["id"])
    wb = (data.get("derived") or {}).get("water_breath")
    assert wb is not None, (
        f"expected derived.water_breath, got: {data.get('derived')!r}"
    )
    assert any(
        "Cap of Water Breathing" in str(s) for s in wb.get("sources") or []
    ), f"expected the cap named in sources, got: {wb!r}"


async def test_cap_of_water_breathing_no_attunement_required(gm_client, roster):
    """The cap needs no attunement — the flag rides alongside Mira's other
    no-attunement aquatic item. `derived.swim_speed` (from her Ring of
    Swimming) still reports alongside `water_breath` from the same walker."""
    mira = roster["Mira Greenleaf"]
    data = await _sheet_json(gm_client, mira["id"])
    derived = data.get("derived") or {}
    assert derived.get("water_breath") is not None, derived
    assert derived.get("swim_speed") is not None, (
        f"expected swim_speed to still report alongside water_breath, "
        f"got: {derived!r}"
    )


async def test_cap_of_water_breathing_unequip_drops_flag(gm_client, roster):
    """Unequipping the cap removes `derived.water_breath`. Restores the
    original inventory on teardown."""
    mira = roster["Mira Greenleaf"]
    data = await _sheet_json(gm_client, mira["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    idx = next(
        (i for i, it in enumerate(inv)
         if isinstance(it, dict) and it.get("_slug") == _CAP_SLUG),
        None,
    )
    assert idx is not None, "Mira has no Cap of Water Breathing item"
    try:
        inv[idx] = {**inv[idx], "equipped": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/sheet-fields",
            json={"inventory": inv},
        )
        data2 = await _sheet_json(gm_client, mira["id"])
        assert "water_breath" not in (data2.get("derived") or {}), (
            f"expected no water_breath after unequip, got: "
            f"{data2.get('derived')!r}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/sheet-fields",
            json={"inventory": snapshot},
        )
