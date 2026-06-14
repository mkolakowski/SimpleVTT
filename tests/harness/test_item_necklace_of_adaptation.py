"""v2.258.0 — Necklace of Adaptation (RAW DMG p.183, uncommon, attunement):
while worn, the wearer can breathe normally in any environment and has
advantage on saving throws against harmful gases and vapors.

The flag rides the `necklace-of-adaptation` catalog payload (`env_adaptation:
True` + `requires_attunement: True`), aggregates in `_equipped_item_effects`
(boolean OR into a new `env_adaptation` field + `env_adaptation_sources`), and
surfaces on `/sheet-json` as `derived.env_adaptation = {sources}`. Attunement-
gated: the per-payload attunement check drops the flag when worn-but-not-
attuned (the Ring of X-ray Vision pattern). The gas-save advantage is GM-
narrated in v1.

Demo fixture: Garrik Ironside (Fighter) wears it attuned — a frontliner who
eats dragon breath weapons fits the gas-resistance flavor.
"""
from .conftest import CAMPAIGN_ID

_NECKLACE_SLUG = "necklace-of-adaptation"


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_necklace_of_adaptation_exposes_flag(gm_client, roster):
    """Happy path: Garrik's `/sheet-json` reports `derived.env_adaptation`
    with the necklace named in its sources."""
    garrik = roster["Garrik Ironside"]
    data = await _sheet_json(gm_client, garrik["id"])
    ea = (data.get("derived") or {}).get("env_adaptation")
    assert ea is not None, (
        f"expected derived.env_adaptation, got: {data.get('derived')!r}"
    )
    assert any(
        "Necklace of Adaptation" in str(s) for s in ea.get("sources") or []
    ), f"expected the necklace named in sources, got: {ea!r}"


async def test_necklace_of_adaptation_detune_drops_flag(gm_client, roster):
    """Attunement gate: un-attuning the necklace (still equipped) removes
    `derived.env_adaptation`. Restores the original inventory on teardown."""
    garrik = roster["Garrik Ironside"]
    data = await _sheet_json(gm_client, garrik["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    idx = next(
        (i for i, it in enumerate(inv)
         if isinstance(it, dict) and it.get("_slug") == _NECKLACE_SLUG),
        None,
    )
    assert idx is not None, "Garrik has no Necklace of Adaptation item"
    try:
        inv[idx] = {**inv[idx], "attuned": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/sheet-fields",
            json={"inventory": inv},
        )
        data2 = await _sheet_json(gm_client, garrik["id"])
        assert "env_adaptation" not in (data2.get("derived") or {}), (
            f"expected no env_adaptation after detune, got: "
            f"{data2.get('derived')!r}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/sheet-fields",
            json={"inventory": snapshot},
        )


async def test_necklace_of_adaptation_unequip_drops_flag(gm_client, roster):
    """Unequipping the necklace removes `derived.env_adaptation`. Restores
    the original inventory on teardown."""
    garrik = roster["Garrik Ironside"]
    data = await _sheet_json(gm_client, garrik["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    idx = next(
        (i for i, it in enumerate(inv)
         if isinstance(it, dict) and it.get("_slug") == _NECKLACE_SLUG),
        None,
    )
    assert idx is not None, "Garrik has no Necklace of Adaptation item"
    try:
        inv[idx] = {**inv[idx], "equipped": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/sheet-fields",
            json={"inventory": inv},
        )
        data2 = await _sheet_json(gm_client, garrik["id"])
        assert "env_adaptation" not in (data2.get("derived") or {}), (
            f"expected no env_adaptation after unequip, got: "
            f"{data2.get('derived')!r}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/sheet-fields",
            json={"inventory": snapshot},
        )
