"""v2.303.0 — Boots of Striding and Springing (RAW DMG p.156, uncommon,
attunement): while worn, your walking speed becomes 30 ft (unless higher),
your speed isn't reduced by encumbrance/heavy armor, and you can jump three
times the normal distance.

The tripled-jump half rides the v2.260.0 `jump_at_will` boolean substrate
(the Ring of Jumping flag): a `jump_at_will: True` + `requires_attunement:
True` payload that aggregates in `_equipped_item_effects` (boolean OR into
`jump_at_will` + `jump_at_will_sources`) and surfaces on `/sheet-json` as
`derived.jump_at_will = {sources}`. Attunement-gated: the per-payload
attunement check drops the flag when worn-but-not-attuned. The 30-ft-floor
walking speed + ignore-encumbrance/heavy-armor clause is GM-narrated in v1.

Carrier: Sir Caelan Lightbringer (Paladin) holds the boots as inert spare loot
(equipped=False/attuned=False). He has no other `jump_at_will` item (his Ring
of Feather Falling is the distinct `feather_fall` flag), so the inert baseline
cleanly proves the boots are the source. Tests PATCH them equipped+attuned,
read the derived flag, then restore.
"""
from .conftest import CAMPAIGN_ID

_BOOTS_SLUG = "boots-of-striding-and-springing"


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


async def _patch_item(gm_client, char_id, slug, *, equipped, attuned):
    snapshot = await _snapshot_inv(gm_client, char_id)
    new_inv = [dict(it) if isinstance(it, dict) else it for it in snapshot]
    found = False
    for it in new_inv:
        if isinstance(it, dict) and it.get("_slug") == slug:
            it["equipped"] = equipped
            it["attuned"] = attuned
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


async def test_boots_equipped_exposes_flag(gm_client, roster):
    """Equipping + attuning the boots surfaces `derived.jump_at_will` with the
    boots named in its sources."""
    caelan = roster["Sir Caelan Lightbringer"]
    cid = caelan["id"]
    snap = await _patch_item(gm_client, cid, _BOOTS_SLUG, equipped=True, attuned=True)
    try:
        derived = (await _sheet_json(gm_client, cid)).get("derived") or {}
        jaw = derived.get("jump_at_will")
        assert jaw is not None, f"expected derived.jump_at_will, got: {derived!r}"
        assert any(
            "Boots of Striding and Springing" in str(s)
            for s in jaw.get("sources") or []
        ), f"expected the boots in jump_at_will sources, got: {jaw!r}"
    finally:
        await _restore(gm_client, cid, snap)


async def test_boots_detune_drops_flag(gm_client, roster):
    """Attunement gate: equipped-but-not-attuned grants nothing."""
    caelan = roster["Sir Caelan Lightbringer"]
    cid = caelan["id"]
    snap = await _patch_item(gm_client, cid, _BOOTS_SLUG, equipped=True, attuned=True)
    try:
        derived = (await _sheet_json(gm_client, cid)).get("derived") or {}
        assert derived.get("jump_at_will") is not None, derived
        await _patch_item(gm_client, cid, _BOOTS_SLUG, equipped=True, attuned=False)
        derived2 = (await _sheet_json(gm_client, cid)).get("derived") or {}
        assert "jump_at_will" not in derived2, (
            f"expected no jump_at_will after detune, got: {derived2!r}"
        )
    finally:
        await _restore(gm_client, cid, snap)


async def test_boots_baseline_has_no_flag(gm_client, roster):
    """Control: with the boots inert (seed, equipped=False), Caelan has no
    jump_at_will source — proving the flag is boots-sourced."""
    caelan = roster["Sir Caelan Lightbringer"]
    derived = (await _sheet_json(gm_client, caelan["id"])).get("derived") or {}
    assert "jump_at_will" not in derived, (
        f"expected no jump_at_will at baseline, got: {derived!r}"
    )


async def test_boots_unequip_drops_flag(gm_client, roster):
    """Equip+attune then unequip removes the flag. Restores on teardown."""
    caelan = roster["Sir Caelan Lightbringer"]
    cid = caelan["id"]
    snap = await _patch_item(gm_client, cid, _BOOTS_SLUG, equipped=True, attuned=True)
    try:
        derived = (await _sheet_json(gm_client, cid)).get("derived") or {}
        assert derived.get("jump_at_will") is not None, derived
        await _patch_item(gm_client, cid, _BOOTS_SLUG, equipped=False, attuned=False)
        derived2 = (await _sheet_json(gm_client, cid)).get("derived") or {}
        assert "jump_at_will" not in derived2, (
            f"expected no jump_at_will after unequip, got: {derived2!r}"
        )
    finally:
        await _restore(gm_client, cid, snap)
