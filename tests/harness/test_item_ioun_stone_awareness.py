"""v2.231.0 — Ioun Stone of Awareness (RAW DMG p.176, rare, attunement):
the fourth non-ability Ioun variant on the shared `ioun-stone` slug, and the
first to surface an awareness passive.

RAW: a dark blue rhomboid that orbits your head; while it does, you can't be
surprised. The flag rides the inventory item via `_cannot_be_surprised: True`
(no ability payload), aggregates in `_equipped_item_effects` (boolean OR into
`cannot_be_surprised`), and surfaces on `/sheet-json` as
`derived.cannot_be_surprised = {sources}`.

Demo fixture: Krieger Stonefist (Barbarian) wears an equipped + attuned Ioun
Stone of Awareness, so the can't-be-surprised flag surfaces.

v2.249.0 — the Ioun Stone of Wisdom was detuned (kept equipped) to free
Krieger's 3rd attunement slot for the Brooch of Shielding, so the old
"coexists with the WIS ioun" assertion was repointed to prove the Awareness
flag now composes with the Brooch's force resistance instead.
"""
from .conftest import CAMPAIGN_ID

_IOUN_SLUG = "ioun-stone"


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_awareness_exposes_cannot_be_surprised_on_sheet_json(gm_client, roster):
    """Happy path: Krieger's `/sheet-json` reports `derived.cannot_be_surprised`
    with the stone named in its sources."""
    krieger = roster["Krieger Stonefist"]
    data = await _sheet_json(gm_client, krieger["id"])
    awareness = (data.get("derived") or {}).get("cannot_be_surprised")
    assert awareness is not None, (
        f"expected derived.cannot_be_surprised, got: {data.get('derived')!r}"
    )
    assert any(
        "Ioun Stone of Awareness" in str(s)
        for s in awareness.get("sources") or []
    ), f"expected the stone named in sources, got: {awareness!r}"


async def test_awareness_coexists_with_brooch_resistance(gm_client, roster):
    """Krieger's attuned items compose: the Awareness stone sets the
    can't-be-surprised flag while the Brooch of Shielding adds force
    resistance, proving distinct items surface independent derived effects
    without interfering. (The Ioun Stone of Wisdom was detuned in v2.249.0 to
    free the slot, so its WIS bonus no longer applies.)"""
    krieger = roster["Krieger Stonefist"]
    data = await _sheet_json(gm_client, krieger["id"])
    derived = data.get("derived") or {}
    assert derived.get("cannot_be_surprised") is not None, derived
    resistances = derived.get("resistances") or {}
    types = [str(t).lower() for t in (resistances.get("types") or [])]
    assert "force" in types, (
        f"expected force resistance from the Brooch, got: {resistances!r}"
    )


async def test_awareness_unequip_drops_flag(gm_client, roster):
    """Unequipping the Awareness stone removes `derived.cannot_be_surprised`.
    Restores the original inventory on teardown."""
    krieger = roster["Krieger Stonefist"]
    data = await _sheet_json(gm_client, krieger["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    idx = next(
        (i for i, it in enumerate(inv)
         if isinstance(it, dict)
         and it.get("_slug") == _IOUN_SLUG
         and it.get("_cannot_be_surprised")),
        None,
    )
    assert idx is not None, "Krieger has no Ioun Stone of Awareness item"
    try:
        inv[idx] = {**inv[idx], "equipped": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-fields",
            json={"inventory": inv},
        )
        data2 = await _sheet_json(gm_client, krieger["id"])
        assert "cannot_be_surprised" not in (data2.get("derived") or {}), (
            f"expected no cannot_be_surprised after unequip, got: {data2.get('derived')!r}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-fields",
            json={"inventory": snapshot},
        )
