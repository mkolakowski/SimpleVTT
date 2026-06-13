"""v2.229.0 — Ioun Stone of Reserve (RAW DMG p.176, rare, attunement): the
second non-ability Ioun variant on the shared `ioun-stone` slug, and the
first item to surface a stored-spell capacity.

RAW: a pearly-white spindle that orbits your head and can store up to 3
levels of spells cast into it. The capacity rides the inventory item via
`_spell_reserve_levels: 3` (no ability payload) and aggregates in
`_equipped_item_effects`, surfacing on `/sheet-json` as
`derived.spell_reserve = {levels, sources}`. (The cast-into / cast-from
mechanic is descriptive-only in v1; this exposes the capacity.)

Demo fixture: Sir Caelan Lightbringer (Paladin half-caster) wears an
equipped + attuned Ioun Stone of Reserve — his 3rd attuned item (after the
Dragon Slayer Longsword + Ioun Stone of Dexterity, RAW max 3) and his
SECOND ioun stone, proving two stones compose on the one slug with
different per-item riders.
"""
from .conftest import CAMPAIGN_ID

_IOUN_SLUG = "ioun-stone"


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_reserve_exposes_spell_reserve_on_sheet_json(gm_client, roster):
    """Happy path: Caelan's `/sheet-json` reports `derived.spell_reserve`
    with `levels == 3` and the stone named in its sources."""
    caelan = roster["Sir Caelan Lightbringer"]
    data = await _sheet_json(gm_client, caelan["id"])
    reserve = (data.get("derived") or {}).get("spell_reserve") or {}
    assert reserve.get("levels") == 3, (
        f"expected derived.spell_reserve.levels == 3, got: {reserve!r}"
    )
    assert any("Ioun Stone of Reserve" in str(s) for s in reserve.get("sources") or []), (
        f"expected the stone named in sources, got: {reserve!r}"
    )


async def test_reserve_coexists_with_dexterity_ioun(gm_client, roster):
    """Caelan's two ioun stones compose: the Reserve stone surfaces the
    spell buffer while the Dexterity stone still raises DEX (10 → 12),
    proving two stones share the `ioun-stone` slug via distinct per-item
    riders without interfering."""
    caelan = roster["Sir Caelan Lightbringer"]
    data = await _sheet_json(gm_client, caelan["id"])
    derived = data.get("derived") or {}
    assert (derived.get("spell_reserve") or {}).get("levels") == 3, derived
    eff = derived.get("effective_abilities") or {}
    assert "DEX" in eff, f"expected DEX override from the second stone, got {eff!r}"
    assert eff["DEX"]["base"] == 10 and eff["DEX"]["effective"] == 12, eff["DEX"]


async def test_reserve_unequip_drops_capacity(gm_client, roster):
    """Unequipping the Reserve stone removes `derived.spell_reserve`.
    Restores the original inventory on teardown."""
    caelan = roster["Sir Caelan Lightbringer"]
    data = await _sheet_json(gm_client, caelan["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    idx = next(
        (i for i, it in enumerate(inv)
         if isinstance(it, dict)
         and it.get("_slug") == _IOUN_SLUG
         and it.get("_spell_reserve_levels")),
        None,
    )
    assert idx is not None, "Caelan has no Ioun Stone of Reserve item"
    try:
        inv[idx] = {**inv[idx], "equipped": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/sheet-fields",
            json={"inventory": inv},
        )
        data2 = await _sheet_json(gm_client, caelan["id"])
        assert "spell_reserve" not in (data2.get("derived") or {}), (
            f"expected no spell_reserve after unequip, got: {data2.get('derived')!r}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/sheet-fields",
            json={"inventory": snapshot},
        )
