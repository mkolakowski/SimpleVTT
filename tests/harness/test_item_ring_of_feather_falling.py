"""v2.244.0 — Ring of Feather Falling (RAW DMG p.191, rare, attunement):
when you fall while wearing this ring, you descend 60 feet per round and
take no falling damage.

The flag rides the `ring-of-feather-falling` catalog payload
(`feather_fall: True`, `requires_attunement: True`), aggregates in
`_equipped_item_effects` (boolean OR into a new `feather_fall` field +
`feather_fall_sources`), and surfaces on `/sheet-json` as
`derived.feather_fall = {sources}`. Unlike the no-attunement Ring of Water
Walking / Ring of Swimming earlier in this batch, this ring is
ATTUNEMENT-gated — the walker's per-payload attunement check filters it when
`attuned` is False.

Demo fixture: Sir Caelan Lightbringer (Paladin) wears it — it fills the 3rd
attunement slot freed by the v2.243.0 Dragon Slayer RAW correction (Caelan
back to 3/3: Ioun Stone of Dexterity + Ioun Stone of Reserve + this ring).
"""
from .conftest import CAMPAIGN_ID

_RING_SLUG = "ring-of-feather-falling"


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


async def test_ring_of_feather_falling_exposes_flag(gm_client, roster):
    """Happy path: Caelan's `/sheet-json` reports `derived.feather_fall`
    with the ring named in its sources."""
    caelan = roster["Sir Caelan Lightbringer"]
    data = await _sheet_json(gm_client, caelan["id"])
    ff = (data.get("derived") or {}).get("feather_fall")
    assert ff is not None, (
        f"expected derived.feather_fall, got: {data.get('derived')!r}"
    )
    assert any(
        "Ring of Feather Falling" in str(s) for s in ff.get("sources") or []
    ), f"expected the ring named in sources, got: {ff!r}"


async def test_ring_of_feather_falling_requires_attunement(gm_client, roster):
    """Unlike the swim/water-walk rings, this one IS attunement-gated.
    Detuning the ring via /attune drops `derived.feather_fall`. Restores
    the seed attunement on teardown."""
    caelan = roster["Sir Caelan Lightbringer"]
    data = await _sheet_json(gm_client, caelan["id"])
    idx = _ring_index(data)
    assert idx is not None, "Caelan has no Ring of Feather Falling item"
    try:
        detune = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/attune",
            json={"inventory_index": idx, "attuned": False},
        )
        assert detune.status_code == 200, detune.text
        data2 = await _sheet_json(gm_client, caelan["id"])
        assert "feather_fall" not in (data2.get("derived") or {}), (
            f"expected no feather_fall once detuned, got: "
            f"{data2.get('derived')!r}"
        )
    finally:
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/attune",
            json={"inventory_index": idx, "attuned": True},
        )


async def test_ring_of_feather_falling_unequip_drops_flag(gm_client, roster):
    """Unequipping the ring removes `derived.feather_fall`. Restores the
    original inventory on teardown."""
    caelan = roster["Sir Caelan Lightbringer"]
    data = await _sheet_json(gm_client, caelan["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    idx = _ring_index(data)
    assert idx is not None, "Caelan has no Ring of Feather Falling item"
    try:
        inv[idx] = {**inv[idx], "equipped": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/sheet-fields",
            json={"inventory": inv},
        )
        data2 = await _sheet_json(gm_client, caelan["id"])
        assert "feather_fall" not in (data2.get("derived") or {}), (
            f"expected no feather_fall after unequip, got: "
            f"{data2.get('derived')!r}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/sheet-fields",
            json={"inventory": snapshot},
        )
