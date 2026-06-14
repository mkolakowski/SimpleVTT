"""v2.260.0 — Ring of Jumping (RAW DMG p.191, uncommon, attunement): while
worn, the wearer can cast the jump spell on themselves at will as a bonus
action.

The flag rides the `ring-of-jumping` catalog payload (`jump_at_will: True` +
`requires_attunement: True`), aggregates in `_equipped_item_effects` (boolean
OR into a new `jump_at_will` field + `jump_at_will_sources`), and surfaces on
`/sheet-json` as `derived.jump_at_will = {sources}`. Attunement-gated: the
per-payload attunement check drops the flag when worn-but-not-attuned (the
Ring of X-ray Vision pattern). The tripled jump distance is GM-narrated in v1.

Demo fixture: Kael Brightleaf (Monk) wears it attuned — on-theme alongside
his Step of the Wind Ki option.
"""
from .conftest import CAMPAIGN_ID

_RING_SLUG = "ring-of-jumping"


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_ring_of_jumping_exposes_flag(gm_client, roster):
    """Happy path: Kael's `/sheet-json` reports `derived.jump_at_will` with the
    ring named in its sources."""
    kael = roster["Kael Brightleaf"]
    data = await _sheet_json(gm_client, kael["id"])
    jaw = (data.get("derived") or {}).get("jump_at_will")
    assert jaw is not None, (
        f"expected derived.jump_at_will, got: {data.get('derived')!r}"
    )
    assert any(
        "Ring of Jumping" in str(s) for s in jaw.get("sources") or []
    ), f"expected the ring named in sources, got: {jaw!r}"


async def test_ring_of_jumping_detune_drops_flag(gm_client, roster):
    """Attunement gate: un-attuning the ring (still equipped) removes
    `derived.jump_at_will`. Restores the original inventory on teardown."""
    kael = roster["Kael Brightleaf"]
    data = await _sheet_json(gm_client, kael["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    idx = next(
        (i for i, it in enumerate(inv)
         if isinstance(it, dict) and it.get("_slug") == _RING_SLUG),
        None,
    )
    assert idx is not None, "Kael has no Ring of Jumping item"
    try:
        inv[idx] = {**inv[idx], "attuned": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{kael['id']}/sheet-fields",
            json={"inventory": inv},
        )
        data2 = await _sheet_json(gm_client, kael["id"])
        assert "jump_at_will" not in (data2.get("derived") or {}), (
            f"expected no jump_at_will after detune, got: "
            f"{data2.get('derived')!r}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{kael['id']}/sheet-fields",
            json={"inventory": snapshot},
        )


async def test_ring_of_jumping_unequip_drops_flag(gm_client, roster):
    """Unequipping the ring removes `derived.jump_at_will`. Restores the
    original inventory on teardown."""
    kael = roster["Kael Brightleaf"]
    data = await _sheet_json(gm_client, kael["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    idx = next(
        (i for i, it in enumerate(inv)
         if isinstance(it, dict) and it.get("_slug") == _RING_SLUG),
        None,
    )
    assert idx is not None, "Kael has no Ring of Jumping item"
    try:
        inv[idx] = {**inv[idx], "equipped": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{kael['id']}/sheet-fields",
            json={"inventory": inv},
        )
        data2 = await _sheet_json(gm_client, kael["id"])
        assert "jump_at_will" not in (data2.get("derived") or {}), (
            f"expected no jump_at_will after unequip, got: "
            f"{data2.get('derived')!r}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{kael['id']}/sheet-fields",
            json={"inventory": snapshot},
        )
