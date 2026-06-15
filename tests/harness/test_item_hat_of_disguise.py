"""v2.321.0 — Hat of Disguise (RAW DMG p.173, rare, attunement): while
wearing the hat you can use an action to cast disguise self at will. The
mechanical surface is the new `disguise_self_at_will` boolean derived flag
— mirrors the v2.284.0 Boots of Levitation `levitate_at_will` substrate
(catalog row → `_equipped_item_effects` init + walker boolean-OR →
`/sheet-json` derived projection). Attunement-gated: the per-payload
attunement check drops the flag when worn-but-not-attuned. The action
cost + in-spell mechanics (concentration, 1-hour duration, illusion
investigation at advantage) are GM-narrated in v1.

Carrier: Lyra Sunstrider (Bard) holds the hat as inert spare loot
(equipped=False/attuned=False). She has no other `disguise_self_at_will`
item, so the inert baseline cleanly proves the hat is the source. Tests
PATCH it equipped+attuned via /sheet-fields (which bypasses the /attune
3-item cap, since Lyra is already at 4 seed-attuned items), read the
derived flag, then restore.
"""
from .conftest import CAMPAIGN_ID

_HAT_SLUG = "hat-of-disguise"


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
    assert found, f"Lyra has no {slug} item"
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


async def test_hat_equipped_exposes_flag(gm_client, roster):
    """Equipping + attuning the hat surfaces `derived.disguise_self_at_will`
    with the hat named in its sources."""
    lyra = roster["Lyra Sunstrider"]
    cid = lyra["id"]
    snap = await _patch_item(gm_client, cid, _HAT_SLUG, equipped=True, attuned=True)
    try:
        derived = (await _sheet_json(gm_client, cid)).get("derived") or {}
        flag = derived.get("disguise_self_at_will")
        assert flag is not None, (
            f"expected derived.disguise_self_at_will, got: {derived!r}"
        )
        assert any(
            "Hat of Disguise" in str(s)
            for s in flag.get("sources") or []
        ), f"expected the hat in disguise_self_at_will sources, got: {flag!r}"
    finally:
        await _restore(gm_client, cid, snap)


async def test_hat_detune_drops_flag(gm_client, roster):
    """Attunement gate: equipped-but-not-attuned grants nothing."""
    lyra = roster["Lyra Sunstrider"]
    cid = lyra["id"]
    snap = await _patch_item(gm_client, cid, _HAT_SLUG, equipped=True, attuned=True)
    try:
        derived = (await _sheet_json(gm_client, cid)).get("derived") or {}
        assert derived.get("disguise_self_at_will") is not None, derived
        await _patch_item(gm_client, cid, _HAT_SLUG, equipped=True, attuned=False)
        derived2 = (await _sheet_json(gm_client, cid)).get("derived") or {}
        assert "disguise_self_at_will" not in derived2, (
            f"expected no disguise_self_at_will after detune, got: {derived2!r}"
        )
    finally:
        await _restore(gm_client, cid, snap)


async def test_hat_baseline_has_no_flag(gm_client, roster):
    """The seed state is inert spare loot (equipped=False/attuned=False).
    The baseline /sheet-json should NOT carry the flag — Lyra has no other
    `disguise_self_at_will` item, so the inert hat proves the source-gating."""
    lyra = roster["Lyra Sunstrider"]
    cid = lyra["id"]
    derived = (await _sheet_json(gm_client, cid)).get("derived") or {}
    assert "disguise_self_at_will" not in derived, (
        f"baseline Lyra (hat inert) must NOT carry the flag; got: {derived!r}"
    )


async def test_hat_unequip_drops_flag(gm_client, roster):
    """Equip state matters: attuned-but-not-equipped (RAW edge case) drops
    the flag too — the per-payload check requires BOTH equipped AND attuned
    when `requires_attunement: True`."""
    lyra = roster["Lyra Sunstrider"]
    cid = lyra["id"]
    snap = await _patch_item(gm_client, cid, _HAT_SLUG, equipped=True, attuned=True)
    try:
        derived = (await _sheet_json(gm_client, cid)).get("derived") or {}
        assert derived.get("disguise_self_at_will") is not None, derived
        await _patch_item(gm_client, cid, _HAT_SLUG, equipped=False, attuned=True)
        derived2 = (await _sheet_json(gm_client, cid)).get("derived") or {}
        assert "disguise_self_at_will" not in derived2, (
            f"expected no disguise_self_at_will after unequip, got: {derived2!r}"
        )
    finally:
        await _restore(gm_client, cid, snap)
