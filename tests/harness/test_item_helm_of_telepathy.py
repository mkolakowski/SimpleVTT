"""v2.307.0 — Helm of Telepathy (RAW DMG p.169, uncommon, attunement): while
worn you can communicate telepathically with a focused creature, cast detect
thoughts (action), and once per dawn cast suggestion. The always-on passive —
the ability to communicate telepathically — rides the `telepathy` boolean
substrate (the mind_shield / feather_fall flag path).

The flag rides the `helm-of-telepathy` catalog payload (`telepathy: True`,
attunement-gated), aggregates in `_equipped_item_effects` (boolean OR into
`telepathy` + `telepathy_sources`), and surfaces on `/sheet-json` as
`derived.telepathy = {sources}`. The detect-thoughts / suggestion casts are
descriptive-only in v1.

Demo fixture: Thalindra Moonshadow (Wizard) carries it as inert spare loot
(equipped=False/attuned=False) — she has no other telepathy item, so the
baseline cleanly proves the helm is the source. The tests PATCH it on, read
the projection, then restore the seed inventory.
"""
from .conftest import CAMPAIGN_ID

_HELM_SLUG = "helm-of-telepathy"


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


async def _patch_helm(gm_client, char_id, *, equipped, attuned):
    snapshot = await _snapshot_inv(gm_client, char_id)
    new_inv = [dict(it) if isinstance(it, dict) else it for it in snapshot]
    found = False
    for it in new_inv:
        if isinstance(it, dict) and it.get("_slug") == _HELM_SLUG:
            it["equipped"] = equipped
            it["attuned"] = attuned
            found = True
    assert found, "Thalindra has no helm-of-telepathy item"
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


async def test_helm_exposes_telepathy(gm_client, roster):
    """Happy path: equipping+attuning the helm surfaces `derived.telepathy`
    with the helm named in sources."""
    rid = _thalindra(roster)["id"]
    snap = await _patch_helm(gm_client, rid, equipped=True, attuned=True)
    try:
        data = await _sheet_json(gm_client, rid)
        tel = (data.get("derived") or {}).get("telepathy")
        assert tel is not None, (
            f"expected derived.telepathy, got: {data.get('derived')!r}"
        )
        assert any(
            "Helm of Telepathy" in str(s) for s in tel.get("sources") or []
        ), f"expected the helm named in sources, got: {tel!r}"
    finally:
        await _restore(gm_client, rid, snap)


async def test_helm_requires_attunement(gm_client, roster):
    """The helm is an attunement item — equipped-but-unattuned yields no
    telepathy flag."""
    rid = _thalindra(roster)["id"]
    snap = await _patch_helm(gm_client, rid, equipped=True, attuned=False)
    try:
        derived = (await _sheet_json(gm_client, rid)).get("derived") or {}
        assert "telepathy" not in derived, (
            f"unattuned helm wrongly granted telepathy, got: {derived!r}"
        )
    finally:
        await _restore(gm_client, rid, snap)


async def test_helm_baseline_has_no_flag(gm_client, roster):
    """Control: with the helm inert (seed, equipped=False), Thalindra has no
    telepathy flag — proving it's helm-sourced."""
    rid = _thalindra(roster)["id"]
    derived = (await _sheet_json(gm_client, rid)).get("derived") or {}
    assert "telepathy" not in derived, (
        f"unexpected baseline telepathy, got: {derived!r}"
    )
