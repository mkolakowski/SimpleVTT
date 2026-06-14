"""v2.245.0 — Ring of Mind Shielding (RAW DMG p.192, uncommon, attunement):
while worn you are immune to magic that reads your thoughts, detects lies,
or knows your alignment / creature type.

The flag rides the `ring-of-mind-shielding` catalog payload
(`mind_shield: True`, `requires_attunement: True`), aggregates in
`_equipped_item_effects` (boolean OR into a new `mind_shield` field +
`mind_shield_sources`), and surfaces on `/sheet-json` as
`derived.mind_shield = {sources}`. Like the Ring of Feather Falling (and
unlike the no-attunement Ring of Water Walking / Swimming) it is
ATTUNEMENT-gated — the walker's per-payload attunement check filters it.

Demo fixture: Lyra Sunstrider (Bard) wears it — homed by displacing her
redundant Ioun Stone of Strength (detuned, kept equipped), so she stays at
the RAW 3/3 cap (Demon Slayer Rapier + Staff of Charming + this ring).
"""
from .conftest import CAMPAIGN_ID

_RING_SLUG = "ring-of-mind-shielding"


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _ring_index(data):
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    return next(
        (i for i, it in enumerate(inv)
         if isinstance(it, dict) and it.get("_slug") == _RING_SLUG),
        None,
    )


async def test_ring_of_mind_shielding_exposes_flag(gm_client, roster):
    """Happy path: Lyra's `/sheet-json` reports `derived.mind_shield` with
    the ring named in its sources."""
    lyra = roster["Lyra Sunstrider"]
    data = await _sheet_json(gm_client, lyra["id"])
    ms = (data.get("derived") or {}).get("mind_shield")
    assert ms is not None, (
        f"expected derived.mind_shield, got: {data.get('derived')!r}"
    )
    assert any(
        "Ring of Mind Shielding" in str(s) for s in ms.get("sources") or []
    ), f"expected the ring named in sources, got: {ms!r}"


async def test_ring_of_mind_shielding_requires_attunement(gm_client, roster):
    """Attunement-gated (like the Ring of Feather Falling). Detuning the
    ring via /attune drops `derived.mind_shield`. Restores the seed
    attunement on teardown."""
    lyra = roster["Lyra Sunstrider"]
    data = await _sheet_json(gm_client, lyra["id"])
    idx = _ring_index(data)
    assert idx is not None, "Lyra has no Ring of Mind Shielding item"
    try:
        detune = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/attune",
            json={"inventory_index": idx, "attuned": False},
        )
        assert detune.status_code == 200, detune.text
        data2 = await _sheet_json(gm_client, lyra["id"])
        assert "mind_shield" not in (data2.get("derived") or {}), (
            f"expected no mind_shield once detuned, got: "
            f"{data2.get('derived')!r}"
        )
    finally:
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/attune",
            json={"inventory_index": idx, "attuned": True},
        )


async def test_ring_of_mind_shielding_unequip_drops_flag(gm_client, roster):
    """Unequipping the ring removes `derived.mind_shield`. Restores the
    original inventory on teardown."""
    lyra = roster["Lyra Sunstrider"]
    data = await _sheet_json(gm_client, lyra["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    idx = _ring_index(data)
    assert idx is not None, "Lyra has no Ring of Mind Shielding item"
    try:
        inv[idx] = {**inv[idx], "equipped": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/sheet-fields",
            json={"inventory": inv},
        )
        data2 = await _sheet_json(gm_client, lyra["id"])
        assert "mind_shield" not in (data2.get("derived") or {}), (
            f"expected no mind_shield after unequip, got: "
            f"{data2.get('derived')!r}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/sheet-fields",
            json={"inventory": snapshot},
        )
