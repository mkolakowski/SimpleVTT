"""v2.242.0 — Ring of Swimming (RAW DMG p.193, uncommon, no attunement):
while worn, you have a swimming speed of 40 feet.

The flag rides the `ring-of-swimming` catalog payload (`swim_speed: True`),
aggregates in `_equipped_item_effects` (boolean OR into a new `swim_speed`
field + `swim_speed_sources`), and surfaces on `/sheet-json` as
`derived.swim_speed = {sources}`. No attunement — it rides alongside a full
3/3 attunement loadout.

Demo fixture: Mira Greenleaf (Druid) wears it — no attunement, so it rides
alongside her Vorpal Scimitar + Headband of Intellect + Ioun Stone of
Protection — fitting for a druid at home in rivers and lakes.
"""
from .conftest import CAMPAIGN_ID

_RING_SLUG = "ring-of-swimming"


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_ring_of_swimming_exposes_flag(gm_client, roster):
    """Happy path: Mira's `/sheet-json` reports `derived.swim_speed` with
    the ring named in its sources."""
    mira = roster["Mira Greenleaf"]
    data = await _sheet_json(gm_client, mira["id"])
    sw = (data.get("derived") or {}).get("swim_speed")
    assert sw is not None, (
        f"expected derived.swim_speed, got: {data.get('derived')!r}"
    )
    assert any(
        "Ring of Swimming" in str(s) for s in sw.get("sources") or []
    ), f"expected the ring named in sources, got: {sw!r}"


async def test_ring_of_swimming_no_attunement_required(gm_client, roster):
    """The ring needs no attunement — the flag rides alongside Mira's full
    3/3 attunement loadout. Her Headband of Intellect (effective INT 19) still
    reports alongside `swim_speed` derived from the same sheet."""
    mira = roster["Mira Greenleaf"]
    data = await _sheet_json(gm_client, mira["id"])
    derived = data.get("derived") or {}
    assert derived.get("swim_speed") is not None, derived
    eff = (derived.get("effective_abilities") or {})
    assert (eff.get("INT") or {}).get("effective") == 19, (
        f"expected Headband-driven effective INT 19 alongside swim_speed, "
        f"got: {eff.get('INT')!r}"
    )


async def test_ring_of_swimming_unequip_drops_flag(gm_client, roster):
    """Unequipping the ring removes `derived.swim_speed`. Restores the
    original inventory on teardown."""
    mira = roster["Mira Greenleaf"]
    data = await _sheet_json(gm_client, mira["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    idx = next(
        (i for i, it in enumerate(inv)
         if isinstance(it, dict) and it.get("_slug") == _RING_SLUG),
        None,
    )
    assert idx is not None, "Mira has no Ring of Swimming item"
    try:
        inv[idx] = {**inv[idx], "equipped": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/sheet-fields",
            json={"inventory": inv},
        )
        data2 = await _sheet_json(gm_client, mira["id"])
        assert "swim_speed" not in (data2.get("derived") or {}), (
            f"expected no swim_speed after unequip, got: "
            f"{data2.get('derived')!r}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/sheet-fields",
            json={"inventory": snapshot},
        )
