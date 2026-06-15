"""v2.300.0 — Cloak of the Manta Ray (RAW DMG p.158, uncommon, no attunement):
while worn with its hood up, you can breathe underwater and you have a swimming
speed of 60 feet.

Composes two existing no-attunement boolean substrates in one catalog payload:
`water_breath: True` (the v2.256.0 Cap of Water Breathing flag) + `swim_speed:
True` (the v2.242.0 Ring of Swimming flag). Both aggregate in
`_equipped_item_effects` (boolean OR) and surface on `/sheet-json` as
`derived.water_breath = {sources}` and `derived.swim_speed = {sources}`. No
attunement — it rides alongside the wearer's loadout freely.

Carrier: Rowan Quickbow (Ranger) carries the cloak as inert spare loot
(equipped=False/attuned=False). He has no other water_breath/swim_speed item
(his Ring of Water Walking is a distinct `water_walk` flag), so the inert
baseline cleanly proves the cloak is the source. Tests PATCH it equipped, read
the two derived flags, then restore.
"""
from .conftest import CAMPAIGN_ID

_CLOAK_SLUG = "cloak-of-the-manta-ray"


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _snapshot_inv(gm_client, char_id):
    data = await _sheet_json(gm_client, char_id)
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    return [dict(it) if isinstance(it, dict) else it for it in inv]


async def _patch_item(gm_client, char_id, slug, *, equipped):
    snapshot = await _snapshot_inv(gm_client, char_id)
    new_inv = [dict(it) if isinstance(it, dict) else it for it in snapshot]
    found = False
    for it in new_inv:
        if isinstance(it, dict) and it.get("_slug") == slug:
            it["equipped"] = equipped
            found = True
    assert found, f"carrier has no {slug} item"
    resp = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"inventory": new_inv},
    )
    assert resp.status_code == 200, resp.text
    return snapshot


async def _restore(gm_client, char_id, snapshot):
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"inventory": snapshot},
    )


async def test_cloak_equipped_exposes_both_flags(gm_client, roster):
    """Equipping the cloak surfaces BOTH derived.water_breath and
    derived.swim_speed with the cloak named in each source list."""
    rowan = roster["Rowan Quickbow"]
    rid = rowan["id"]
    snap = await _patch_item(gm_client, rid, _CLOAK_SLUG, equipped=True)
    try:
        derived = (await _sheet_json(gm_client, rid)).get("derived") or {}
        wb = derived.get("water_breath")
        sw = derived.get("swim_speed")
        assert wb is not None, f"expected derived.water_breath, got: {derived!r}"
        assert sw is not None, f"expected derived.swim_speed, got: {derived!r}"
        assert any(
            "Cloak of the Manta Ray" in str(s) for s in wb.get("sources") or []
        ), f"expected the cloak in water_breath sources, got: {wb!r}"
        assert any(
            "Cloak of the Manta Ray" in str(s) for s in sw.get("sources") or []
        ), f"expected the cloak in swim_speed sources, got: {sw!r}"
    finally:
        await _restore(gm_client, rid, snap)


async def test_cloak_no_attunement_required(gm_client, roster):
    """The cloak needs no attunement — equipping it (attuned stays False in the
    seed) is enough to surface both flags."""
    rowan = roster["Rowan Quickbow"]
    rid = rowan["id"]
    snap = await _patch_item(gm_client, rid, _CLOAK_SLUG, equipped=True)
    try:
        inv = await _snapshot_inv(gm_client, rid)
        cloak = next(
            it for it in inv
            if isinstance(it, dict) and it.get("_slug") == _CLOAK_SLUG
        )
        assert not cloak.get("attuned"), (
            f"cloak should grant its flags un-attuned, got: {cloak!r}"
        )
        derived = (await _sheet_json(gm_client, rid)).get("derived") or {}
        assert derived.get("water_breath") is not None, derived
        assert derived.get("swim_speed") is not None, derived
    finally:
        await _restore(gm_client, rid, snap)


async def test_cloak_baseline_has_neither_flag(gm_client, roster):
    """Control: with the cloak inert (seed, equipped=False), Rowan has no
    water_breath/swim_speed source — proving both flags are cloak-sourced."""
    rowan = roster["Rowan Quickbow"]
    derived = (await _sheet_json(gm_client, rowan["id"])).get("derived") or {}
    assert "water_breath" not in derived, (
        f"expected no water_breath at baseline, got: {derived!r}"
    )
    assert "swim_speed" not in derived, (
        f"expected no swim_speed at baseline, got: {derived!r}"
    )


async def test_cloak_unequip_drops_flags(gm_client, roster):
    """Equipping then unequipping the cloak removes both flags. Restores the
    original inventory on teardown."""
    rowan = roster["Rowan Quickbow"]
    rid = rowan["id"]
    snap = await _patch_item(gm_client, rid, _CLOAK_SLUG, equipped=True)
    try:
        derived = (await _sheet_json(gm_client, rid)).get("derived") or {}
        assert derived.get("water_breath") is not None, derived
        await _patch_item(gm_client, rid, _CLOAK_SLUG, equipped=False)
        derived2 = (await _sheet_json(gm_client, rid)).get("derived") or {}
        assert "water_breath" not in derived2, derived2
        assert "swim_speed" not in derived2, derived2
    finally:
        await _restore(gm_client, rid, snap)
