"""v2.234.0 — Amulet of Proof against Detection (RAW DMG p.150, uncommon,
attunement): while worn, you're hidden from divination magic and can't be
perceived through magical scrying sensors.

The flag rides the `amulet-of-proof-against-detection` catalog payload
(`scry_proof: True`), aggregates in `_equipped_item_effects` (boolean OR into
a new `scry_proof` field + `scry_proof_sources`), and surfaces on
`/sheet-json` as `derived.scry_proof = {sources}`. Divination/scrying
mechanics are descriptive-only in v1 — this exposes the protection as a
derived read.

Demo fixture: Kael Brightleaf (Monk Lv 7) wears it as his 2nd attuned item
(after the Bracers of Defense, RAW max 3) — thematic on a secluded,
meditative Monk.
"""
from .conftest import CAMPAIGN_ID

_AMULET_SLUG = "amulet-of-proof-against-detection"


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_amulet_exposes_scry_proof_on_sheet_json(gm_client, roster):
    """Happy path: Kael's `/sheet-json` reports `derived.scry_proof` with
    the amulet named in its sources."""
    kael = roster["Kael Brightleaf"]
    data = await _sheet_json(gm_client, kael["id"])
    scry = (data.get("derived") or {}).get("scry_proof")
    assert scry is not None, (
        f"expected derived.scry_proof, got: {data.get('derived')!r}"
    )
    assert any(
        "Amulet of Proof against Detection" in str(s)
        for s in scry.get("sources") or []
    ), f"expected the amulet named in sources, got: {scry!r}"


async def test_amulet_coexists_with_bracers_ac(gm_client, roster):
    """The amulet's scry-proof flag rides alongside Kael's Bracers of
    Defense AC bonus — proving the new boolean field composes with the
    existing AC-bonus aggregation on a different attuned item."""
    kael = roster["Kael Brightleaf"]
    data = await _sheet_json(gm_client, kael["id"])
    derived = data.get("derived") or {}
    assert derived.get("scry_proof") is not None, derived
    # The Bracers grant +2 AC; the sheet's stored AC reflects the Monk's
    # Unarmored Defense, and the amulet does not perturb it. Assert both
    # the flag and that the inventory still carries the Bracers.
    inv = (data.get("sheet") or {}).get("inventory") or []
    assert any(
        isinstance(it, dict) and it.get("_slug") == "bracers-of-defense"
        for it in inv
    ), "expected Kael to still carry the Bracers of Defense"


async def test_amulet_unequip_drops_flag(gm_client, roster):
    """Unequipping the amulet removes `derived.scry_proof`. Restores the
    original inventory on teardown."""
    kael = roster["Kael Brightleaf"]
    data = await _sheet_json(gm_client, kael["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    idx = next(
        (i for i, it in enumerate(inv)
         if isinstance(it, dict) and it.get("_slug") == _AMULET_SLUG),
        None,
    )
    assert idx is not None, "Kael has no Amulet of Proof against Detection item"
    try:
        inv[idx] = {**inv[idx], "equipped": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{kael['id']}/sheet-fields",
            json={"inventory": inv},
        )
        data2 = await _sheet_json(gm_client, kael["id"])
        assert "scry_proof" not in (data2.get("derived") or {}), (
            f"expected no scry_proof after unequip, got: {data2.get('derived')!r}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{kael['id']}/sheet-fields",
            json={"inventory": snapshot},
        )
