"""v2.315.0 — Scimitar of Speed (RAW DMG p.197, very rare, attunement): you
gain a +2 bonus to attack and damage rolls made with this magic weapon, and
you can make one attack with it as a bonus action on each of your turns.

The marquee bonus-action-attack half rides the v2.315.0 `bonus_action_attack`
boolean substrate (mirroring the telepathy / jump_at_will / feather_fall
flags): a `bonus_action_attack: True` + `requires_attunement: True` payload
that aggregates in `_equipped_item_effects` (boolean OR into
`bonus_action_attack` + `bonus_action_attack_sources`) and surfaces on
`/sheet-json` as `derived.bonus_action_attack = {sources}`. Attunement-gated:
the per-payload attunement check drops the flag when worn-but-not-attuned. The
+2 attack/damage half is baked onto the wielder's attack row when equipped
(Dragon Slayer / Vorpal precedent); the actual extra-attack action-economy is
GM-narrated in v1.

Carrier: Sir Caelan Lightbringer (Paladin) holds the scimitar as inert spare
loot (equipped=False/attuned=False). He has no other `bonus_action_attack`
item, so the inert baseline cleanly proves the scimitar is the source. Tests
PATCH it equipped+attuned, read the derived flag, then restore.
"""
from .conftest import CAMPAIGN_ID

_SCIMITAR_SLUG = "scimitar-of-speed"


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


async def test_scimitar_equipped_exposes_flag(gm_client, roster):
    """Equipping + attuning the scimitar surfaces `derived.bonus_action_attack`
    with the scimitar named in its sources."""
    caelan = roster["Sir Caelan Lightbringer"]
    cid = caelan["id"]
    snap = await _patch_item(gm_client, cid, _SCIMITAR_SLUG, equipped=True, attuned=True)
    try:
        derived = (await _sheet_json(gm_client, cid)).get("derived") or {}
        baa = derived.get("bonus_action_attack")
        assert baa is not None, f"expected derived.bonus_action_attack, got: {derived!r}"
        assert any(
            "Scimitar of Speed" in str(s)
            for s in baa.get("sources") or []
        ), f"expected the scimitar in bonus_action_attack sources, got: {baa!r}"
    finally:
        await _restore(gm_client, cid, snap)


async def test_scimitar_detune_drops_flag(gm_client, roster):
    """Attunement gate: equipped-but-not-attuned grants nothing."""
    caelan = roster["Sir Caelan Lightbringer"]
    cid = caelan["id"]
    snap = await _patch_item(gm_client, cid, _SCIMITAR_SLUG, equipped=True, attuned=True)
    try:
        derived = (await _sheet_json(gm_client, cid)).get("derived") or {}
        assert derived.get("bonus_action_attack") is not None, derived
        await _patch_item(gm_client, cid, _SCIMITAR_SLUG, equipped=True, attuned=False)
        derived2 = (await _sheet_json(gm_client, cid)).get("derived") or {}
        assert "bonus_action_attack" not in derived2, (
            f"expected no bonus_action_attack after detune, got: {derived2!r}"
        )
    finally:
        await _restore(gm_client, cid, snap)


async def test_scimitar_baseline_has_no_flag(gm_client, roster):
    """Control: with the scimitar inert (seed, equipped=False), Caelan has no
    bonus_action_attack source — proving the flag is scimitar-sourced."""
    caelan = roster["Sir Caelan Lightbringer"]
    derived = (await _sheet_json(gm_client, caelan["id"])).get("derived") or {}
    assert "bonus_action_attack" not in derived, (
        f"expected no bonus_action_attack at baseline, got: {derived!r}"
    )


async def test_scimitar_unequip_drops_flag(gm_client, roster):
    """Equip+attune then unequip removes the flag. Restores on teardown."""
    caelan = roster["Sir Caelan Lightbringer"]
    cid = caelan["id"]
    snap = await _patch_item(gm_client, cid, _SCIMITAR_SLUG, equipped=True, attuned=True)
    try:
        derived = (await _sheet_json(gm_client, cid)).get("derived") or {}
        assert derived.get("bonus_action_attack") is not None, derived
        await _patch_item(gm_client, cid, _SCIMITAR_SLUG, equipped=False, attuned=False)
        derived2 = (await _sheet_json(gm_client, cid)).get("derived") or {}
        assert "bonus_action_attack" not in derived2, (
            f"expected no bonus_action_attack after unequip, got: {derived2!r}"
        )
    finally:
        await _restore(gm_client, cid, snap)
