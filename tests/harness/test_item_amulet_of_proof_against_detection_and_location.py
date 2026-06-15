"""v2.294.0 — Amulet of Proof against Detection and Location (RAW DMG p.150,
uncommon, attunement): the "and Location" sibling of the v2.234.0 Amulet of
Proof against Detection. Identical RAW text — while worn you're hidden from
divination magic and can't be perceived through magical scrying sensors —
and the same `scry_proof` boolean substrate.

The flag rides the `amulet-of-proof-against-detection-and-location` catalog
payload (`scry_proof: True`, attunement-gated), aggregates in
`_equipped_item_effects` (boolean OR into `scry_proof` + `scry_proof_sources`),
and surfaces on `/sheet-json` as `derived.scry_proof = {sources}`.
Divination/scrying mechanics are descriptive-only in v1.

Demo fixture: Thalindra Moonshadow (Wizard) carries it as inert spare loot
(equipped=False/attuned=False) — she has no other scry-proof item, so the
baseline cleanly proves the amulet is the source. The tests PATCH it on, read
the projection, then restore the seed inventory.
"""
from .conftest import CAMPAIGN_ID

_AMULET_SLUG = "amulet-of-proof-against-detection-and-location"


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


async def _patch_amulet(gm_client, char_id, *, equipped, attuned):
    snapshot = await _snapshot_inv(gm_client, char_id)
    new_inv = [dict(it) if isinstance(it, dict) else it for it in snapshot]
    found = False
    for it in new_inv:
        if isinstance(it, dict) and it.get("_slug") == _AMULET_SLUG:
            it["equipped"] = equipped
            it["attuned"] = attuned
            found = True
    assert found, "Thalindra has no amulet-of-proof-against-detection-and-location item"
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


def _thalindra(roster):
    return next(v for k, v in roster.items() if "Thalindra" in k)


async def test_amulet_exposes_scry_proof(gm_client, roster):
    """Happy path: equipping+attuning the amulet surfaces
    `derived.scry_proof` with the amulet named in sources."""
    rid = _thalindra(roster)["id"]
    snap = await _patch_amulet(gm_client, rid, equipped=True, attuned=True)
    try:
        data = await _sheet_json(gm_client, rid)
        scry = (data.get("derived") or {}).get("scry_proof")
        assert scry is not None, (
            f"expected derived.scry_proof, got: {data.get('derived')!r}"
        )
        assert any(
            "Amulet of Proof against Detection and Location" in str(s)
            for s in scry.get("sources") or []
        ), f"expected the amulet named in sources, got: {scry!r}"
    finally:
        await _restore(gm_client, rid, snap)


async def test_amulet_requires_attunement(gm_client, roster):
    """The amulet is an attunement item — equipped-but-unattuned yields no
    scry-proof flag."""
    rid = _thalindra(roster)["id"]
    snap = await _patch_amulet(gm_client, rid, equipped=True, attuned=False)
    try:
        derived = (await _sheet_json(gm_client, rid)).get("derived") or {}
        assert "scry_proof" not in derived, (
            f"unattuned amulet wrongly granted scry_proof, got: {derived!r}"
        )
    finally:
        await _restore(gm_client, rid, snap)


async def test_amulet_baseline_has_no_flag(gm_client, roster):
    """Control: with the amulet inert (seed, equipped=False), Thalindra has
    no scry-proof flag — proving it's amulet-sourced."""
    rid = _thalindra(roster)["id"]
    derived = (await _sheet_json(gm_client, rid)).get("derived") or {}
    assert "scry_proof" not in derived, (
        f"unexpected baseline scry_proof, got: {derived!r}"
    )
