"""v2.257.0 — Ring of X-ray Vision (RAW DMG p.193, rare, attunement):
while attuned and worn, the wearer can see into and through solid matter
(30-ft radius; 1 ft of stone / 1 in. of metal / 3 ft of wood or dirt blocks
it).

The flag rides the `ring-of-x-ray-vision` catalog payload (`xray_vision:
True` + `requires_attunement: True`), aggregates in `_equipped_item_effects`
(boolean OR into a new `xray_vision` field + `xray_vision_sources`), and
surfaces on `/sheet-json` as `derived.xray_vision = {sources}`. Attunement-
gated: the per-payload attunement check drops the flag when the ring is
worn-but-not-attuned (the Cloak of Elvenkind / Eyes of the Eagle pattern).

Demo fixture: Magnus Hexbinder (Warlock) wears it attuned as his 4th attuned
item — seed-load bypasses the RAW 3-item cap (enforced at /attune runtime
only). On-theme alongside his Devil's Sight invocation.
"""
from .conftest import CAMPAIGN_ID

_RING_SLUG = "ring-of-x-ray-vision"


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_ring_of_x_ray_vision_exposes_flag(gm_client, roster):
    """Happy path: Magnus's `/sheet-json` reports `derived.xray_vision` with
    the ring named in its sources."""
    magnus = roster["Magnus Hexbinder"]
    data = await _sheet_json(gm_client, magnus["id"])
    xv = (data.get("derived") or {}).get("xray_vision")
    assert xv is not None, (
        f"expected derived.xray_vision, got: {data.get('derived')!r}"
    )
    assert any(
        "Ring of X-ray Vision" in str(s) for s in xv.get("sources") or []
    ), f"expected the ring named in sources, got: {xv!r}"


async def test_ring_of_x_ray_vision_detune_drops_flag(gm_client, roster):
    """Attunement gate: un-attuning the ring (still equipped) removes
    `derived.xray_vision`. Restores the original inventory on teardown."""
    magnus = roster["Magnus Hexbinder"]
    data = await _sheet_json(gm_client, magnus["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    idx = next(
        (i for i, it in enumerate(inv)
         if isinstance(it, dict) and it.get("_slug") == _RING_SLUG),
        None,
    )
    assert idx is not None, "Magnus has no Ring of X-ray Vision item"
    try:
        inv[idx] = {**inv[idx], "attuned": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
            json={"inventory": inv},
        )
        data2 = await _sheet_json(gm_client, magnus["id"])
        assert "xray_vision" not in (data2.get("derived") or {}), (
            f"expected no xray_vision after detune, got: "
            f"{data2.get('derived')!r}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
            json={"inventory": snapshot},
        )


async def test_ring_of_x_ray_vision_unequip_drops_flag(gm_client, roster):
    """Unequipping the ring removes `derived.xray_vision`. Restores the
    original inventory on teardown."""
    magnus = roster["Magnus Hexbinder"]
    data = await _sheet_json(gm_client, magnus["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    idx = next(
        (i for i, it in enumerate(inv)
         if isinstance(it, dict) and it.get("_slug") == _RING_SLUG),
        None,
    )
    assert idx is not None, "Magnus has no Ring of X-ray Vision item"
    try:
        inv[idx] = {**inv[idx], "equipped": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
            json={"inventory": inv},
        )
        data2 = await _sheet_json(gm_client, magnus["id"])
        assert "xray_vision" not in (data2.get("derived") or {}), (
            f"expected no xray_vision after unequip, got: "
            f"{data2.get('derived')!r}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
            json={"inventory": snapshot},
        )
