"""v2.236.0 — Mantle of Spell Resistance (RAW DMG p.180, rare, attunement):
while worn, you have advantage on saving throws against spells.

The flag rides the `mantle-of-spell-resistance` catalog payload
(`spell_save_advantage: True`), aggregates in `_equipped_item_effects`
(boolean OR into a new `spell_save_advantage` field +
`spell_save_advantage_sources`), and surfaces on `/sheet-json` as
`derived.spell_save_advantage = {sources}`. The advantage is descriptive-only
in v1 — this exposes the protection as a derived read; the save resolver
doesn't yet fold it into rolls automatically.

Demo fixture: Quan Reelstep (Way of the Drunken Master Monk) wears it as his
3rd attuned item (Belt of Dwarvenkind + Ioun Stone of Mastery + this mantle,
RAW max 3) — a monk deflecting hostile magic with a flowing mantle.
"""
from .conftest import CAMPAIGN_ID

_MANTLE_SLUG = "mantle-of-spell-resistance"


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_mantle_exposes_spell_save_advantage(gm_client, roster):
    """Happy path: Quan's `/sheet-json` reports `derived.spell_save_advantage`
    with the mantle named in its sources."""
    quan = roster["Quan Reelstep"]
    data = await _sheet_json(gm_client, quan["id"])
    ssa = (data.get("derived") or {}).get("spell_save_advantage")
    assert ssa is not None, (
        f"expected derived.spell_save_advantage, got: {data.get('derived')!r}"
    )
    assert any(
        "Mantle of Spell Resistance" in str(s) for s in ssa.get("sources") or []
    ), f"expected the mantle named in sources, got: {ssa!r}"


async def test_mantle_coexists_with_other_attuned_items(gm_client, roster):
    """The mantle's spell-save-advantage flag composes with Quan's existing
    attuned-item effects: the Ioun Stone of Mastery's proficiency bonus
    (PB 3 → 4) is still reported, proving the new boolean field rides
    alongside the proficiency-bonus aggregation on a different item."""
    quan = roster["Quan Reelstep"]
    data = await _sheet_json(gm_client, quan["id"])
    derived = data.get("derived") or {}
    assert derived.get("spell_save_advantage") is not None, derived
    pb = derived.get("proficiency_bonus") or {}
    assert pb.get("effective") == 4, (
        f"expected the Mastery stone's PB 4 to still report, got: {pb!r}"
    )


async def test_mantle_unequip_drops_flag(gm_client, roster):
    """Unequipping the mantle removes `derived.spell_save_advantage`.
    Restores the original inventory on teardown."""
    quan = roster["Quan Reelstep"]
    data = await _sheet_json(gm_client, quan["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    idx = next(
        (i for i, it in enumerate(inv)
         if isinstance(it, dict) and it.get("_slug") == _MANTLE_SLUG),
        None,
    )
    assert idx is not None, "Quan has no Mantle of Spell Resistance item"
    try:
        inv[idx] = {**inv[idx], "equipped": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{quan['id']}/sheet-fields",
            json={"inventory": inv},
        )
        data2 = await _sheet_json(gm_client, quan["id"])
        assert "spell_save_advantage" not in (data2.get("derived") or {}), (
            f"expected no spell_save_advantage after unequip, got: "
            f"{data2.get('derived')!r}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{quan['id']}/sheet-fields",
            json={"inventory": snapshot},
        )
