"""v2.238.0 — Winged Boots (RAW DMG p.214, uncommon, attunement): while
worn, you have a flying speed equal to your walking speed (you can fly for up
to 4 hours, all at once or in several shorter flights).

The flag rides the `winged-boots` catalog payload (`flying_speed: True`,
`requires_attunement: True`), aggregates in `_equipped_item_effects` (boolean
OR into a new `flying_speed` field + `flying_speed_sources`), and surfaces on
`/sheet-json` as `derived.flying_speed = {sources}`. The 4-hour charge budget
is GM-narrated in v1 — this exposes the ability as a derived read.

Demo fixture: Kael Brightleaf (Way of the Open Hand Monk) wears them as his
3rd attuned item (after Bracers of Defense + Amulet of Proof against
Detection) — on-theme for a fast, mobile monk.
"""
from .conftest import CAMPAIGN_ID

_BOOTS_SLUG = "winged-boots"


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_winged_boots_expose_flying_speed(gm_client, roster):
    """Happy path: Kael's `/sheet-json` reports `derived.flying_speed` with
    the boots named in its sources."""
    kael = roster["Kael Brightleaf"]
    data = await _sheet_json(gm_client, kael["id"])
    fs = (data.get("derived") or {}).get("flying_speed")
    assert fs is not None, (
        f"expected derived.flying_speed, got: {data.get('derived')!r}"
    )
    assert any(
        "Winged Boots" in str(s) for s in fs.get("sources") or []
    ), f"expected the boots named in sources, got: {fs!r}"


async def test_winged_boots_require_attunement(gm_client, roster):
    """The boots are an attunement item — the flag only surfaces while
    `attuned: True`. Dropping attunement removes `derived.flying_speed`;
    restores the original inventory on teardown."""
    kael = roster["Kael Brightleaf"]
    data = await _sheet_json(gm_client, kael["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    idx = next(
        (i for i, it in enumerate(inv)
         if isinstance(it, dict) and it.get("_slug") == _BOOTS_SLUG),
        None,
    )
    assert idx is not None, "Kael has no Winged Boots item"
    try:
        inv[idx] = {**inv[idx], "attuned": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{kael['id']}/sheet-fields",
            json={"inventory": inv},
        )
        data2 = await _sheet_json(gm_client, kael["id"])
        assert "flying_speed" not in (data2.get("derived") or {}), (
            f"expected no flying_speed after un-attune, got: "
            f"{data2.get('derived')!r}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{kael['id']}/sheet-fields",
            json={"inventory": snapshot},
        )


async def test_winged_boots_compose_with_scry_proof(gm_client, roster):
    """The flying-speed flag rides alongside Kael's Amulet of Proof against
    Detection — both equipped wondrous items contribute their own derived
    surfaces from the same equipped-item walker."""
    kael = roster["Kael Brightleaf"]
    data = await _sheet_json(gm_client, kael["id"])
    derived = data.get("derived") or {}
    assert derived.get("flying_speed") is not None, derived
    assert derived.get("scry_proof") is not None, (
        f"expected scry_proof to still report alongside flying_speed, "
        f"got: {derived!r}"
    )
