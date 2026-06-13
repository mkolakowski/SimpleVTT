"""v2.233.0 — Periapt of Health (RAW DMG p.184, uncommon, no attunement):
while worn, you're immune to contracting disease.

The flag rides the `periapt-of-health` catalog payload (`disease_immune:
True`), aggregates in `_equipped_item_effects` (boolean OR into a new
`disease_immune` field + `disease_immune_sources`), and surfaces on
`/sheet-json` as `derived.disease_immune = {sources}`. Disease mechanics are
descriptive-only in v1 — this exposes the immunity as a derived read.

Demo fixture: Brother Tavik Stonebrow (Cleric Lv 8) wears it. It requires no
attunement, so it composes with his three attuned items (Ring of Protection,
Staff of Healing, Amulet of Health) without exceeding the RAW cap of 3.
"""
from .conftest import CAMPAIGN_ID

_PERIAPT_SLUG = "periapt-of-health"


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_periapt_exposes_disease_immune_on_sheet_json(gm_client, roster):
    """Happy path: Tavik's `/sheet-json` reports `derived.disease_immune`
    with the periapt named in its sources."""
    tavik = roster["Brother Tavik Stonebrow"]
    data = await _sheet_json(gm_client, tavik["id"])
    immune = (data.get("derived") or {}).get("disease_immune")
    assert immune is not None, (
        f"expected derived.disease_immune, got: {data.get('derived')!r}"
    )
    assert any(
        "Periapt of Health" in str(s)
        for s in immune.get("sources") or []
    ), f"expected the periapt named in sources, got: {immune!r}"


async def test_periapt_coexists_with_attuned_items(gm_client, roster):
    """The periapt needs no attunement, so the disease-immunity flag and
    Tavik's Amulet of Health CON override compose without conflict — proving
    the new boolean field rides alongside the existing ability/HP overrides."""
    tavik = roster["Brother Tavik Stonebrow"]
    data = await _sheet_json(gm_client, tavik["id"])
    derived = data.get("derived") or {}
    assert derived.get("disease_immune") is not None, derived
    eff = derived.get("effective_abilities") or {}
    assert "CON" in eff, f"expected CON override from the amulet, got {eff!r}"
    assert eff["CON"]["effective"] == 19, eff["CON"]


async def test_periapt_unequip_drops_flag(gm_client, roster):
    """Unequipping the periapt removes `derived.disease_immune`. Restores
    the original inventory on teardown."""
    tavik = roster["Brother Tavik Stonebrow"]
    data = await _sheet_json(gm_client, tavik["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    idx = next(
        (i for i, it in enumerate(inv)
         if isinstance(it, dict) and it.get("_slug") == _PERIAPT_SLUG),
        None,
    )
    assert idx is not None, "Tavik has no Periapt of Health item"
    try:
        inv[idx] = {**inv[idx], "equipped": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/sheet-fields",
            json={"inventory": inv},
        )
        data2 = await _sheet_json(gm_client, tavik["id"])
        assert "disease_immune" not in (data2.get("derived") or {}), (
            f"expected no disease_immune after unequip, got: {data2.get('derived')!r}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/sheet-fields",
            json={"inventory": snapshot},
        )
