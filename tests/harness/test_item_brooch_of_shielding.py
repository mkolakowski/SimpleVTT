"""v2.249.0 — Brooch of Shielding (RAW DMG p.156, uncommon, attunement):
"while wearing this brooch you have resistance to force damage and immunity to
the magic missile spell."

Two surfaces compose on the one item:
  - Force *resistance* reuses the v2.235.0 Ring of Resistance substrate — the
    resisted type rides the inventory item via the per-item `_resistance_type`
    rider ("force") on the `brooch-of-shielding` slug. The walker folds it into
    the aggregated `resistance_to` list that `_resistance_halve` consults in the
    live damage pipeline, so force damage to the wearer is halved through
    `PATCH .../sheet-fields`. Surfaces on `/sheet-json` as
    `derived.resistances = {types, sources}`.
  - Magic-missile *immunity* is the new boolean-OR passive `magic_missile_immune`
    — the catalog payload sets it, the walker accumulates it, and it surfaces on
    `/sheet-json` as `derived.magic_missile_immune = {sources}`.

Both are attunement-gated.

Demo fixture: Krieger Stonefist (Barbarian) wears the Brooch of Shielding as his
3rd attuned item (Ioun Stone of Awareness + Boots of Speed + this, RAW max 3) —
homed by detuning his Ioun Stone of Wisdom (kept equipped; the WIS bump was a
secondary-stat read, last in the ability-ioun sacrifice series).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_BROOCH_SLUG = "brooch-of-shielding"


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _brooch_index(data):
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    return next(
        (i for i, it in enumerate(inv)
         if isinstance(it, dict) and it.get("_slug") == _BROOCH_SLUG),
        None,
    )


async def _hp_current(gm_client, char_id):
    data = await _sheet_json(gm_client, char_id)
    sheet = data.get("sheet") or {}
    return int((sheet.get("hp") or {}).get("current") or 0)


async def _deal_damage(gm_client, char_id, naive_current, amount, dtype):
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={
            "hp": {"current": naive_current},
            "hp_change_reason": "damage",
            "damage_amount": amount,
            "damage_type": dtype,
        },
    )


@pytest_asyncio.fixture
async def krieger_hp_restore(gm_client, roster):
    """Snapshot Krieger's HP and restore it after the test so the typed-damage
    PATCHes don't leak into other tests."""
    krieger = roster["Krieger Stonefist"]
    data = await _sheet_json(gm_client, krieger["id"])
    hp = dict((data.get("sheet") or {}).get("hp") or {})
    try:
        yield krieger
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-fields",
            json={"hp": hp},
        )


async def test_brooch_exposes_force_resistance(gm_client, roster):
    """Happy path: Krieger's `/sheet-json` reports `derived.resistances` listing
    force, naming the brooch in its sources."""
    krieger = roster["Krieger Stonefist"]
    data = await _sheet_json(gm_client, krieger["id"])
    derived = data.get("derived") or {}
    res = derived.get("resistances")
    assert res is not None, f"expected derived.resistances, got: {derived!r}"
    assert "force" in (res.get("types") or []), res
    assert any(
        "Brooch of Shielding" in str(s) for s in res.get("sources") or []
    ), f"expected the brooch named in resistance sources, got: {res!r}"


async def test_brooch_exposes_magic_missile_immunity(gm_client, roster):
    """Happy path: Krieger's `/sheet-json` reports `derived.magic_missile_immune`
    with the brooch named in its sources."""
    krieger = roster["Krieger Stonefist"]
    data = await _sheet_json(gm_client, krieger["id"])
    derived = data.get("derived") or {}
    mmi = derived.get("magic_missile_immune")
    assert mmi is not None, (
        f"expected derived.magic_missile_immune, got: {derived!r}"
    )
    assert any(
        "Brooch of Shielding" in str(s) for s in mmi.get("sources") or []
    ), f"expected the brooch named in sources, got: {mmi!r}"


async def test_brooch_halves_force_damage(gm_client, krieger_hp_restore):
    """End-to-end: 20 force damage to the force-resisted wearer drops HP by only
    10 — the equipped + attuned brooch halves it through `_resistance_halve`."""
    krieger = krieger_hp_restore
    before = await _hp_current(gm_client, krieger["id"])
    await _deal_damage(gm_client, krieger["id"], before - 20, 20, "force")
    after = await _hp_current(gm_client, krieger["id"])
    assert after == before - 10, (
        f"force damage not halved by the brooch: {before} → {after} (expected -10)"
    )


async def test_brooch_does_not_halve_other_types(gm_client, krieger_hp_restore):
    """Control: 20 FIRE damage is unaffected by the force-resistance brooch —
    full 20 applies, proving the resistance is type-specific."""
    krieger = krieger_hp_restore
    before = await _hp_current(gm_client, krieger["id"])
    await _deal_damage(gm_client, krieger["id"], before - 20, 20, "fire")
    after = await _hp_current(gm_client, krieger["id"])
    assert after == before - 20, (
        f"fire damage wrongly reduced: {before} → {after} (expected -20)"
    )


async def test_brooch_requires_attunement(gm_client, roster):
    """Attunement-gated. Detuning the brooch via `/attune` drops both the force
    entry from `derived.resistances` and `derived.magic_missile_immune`.
    Restores the seed attunement on teardown."""
    krieger = roster["Krieger Stonefist"]
    data = await _sheet_json(gm_client, krieger["id"])
    idx = _brooch_index(data)
    assert idx is not None, "Krieger has no Brooch of Shielding item"
    try:
        detune = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/attune",
            json={"inventory_index": idx, "attuned": False},
        )
        assert detune.status_code == 200, detune.text
        data2 = await _sheet_json(gm_client, krieger["id"])
        derived2 = data2.get("derived") or {}
        force_resisted = "force" in (
            (derived2.get("resistances") or {}).get("types") or []
        )
        assert not force_resisted, (
            f"expected no force resistance once detuned, got: "
            f"{derived2.get('resistances')!r}"
        )
        assert "magic_missile_immune" not in derived2, (
            f"expected no magic_missile_immune once detuned, got: "
            f"{derived2.get('magic_missile_immune')!r}"
        )
    finally:
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/attune",
            json={"inventory_index": idx, "attuned": True},
        )


async def test_brooch_unequip_drops_both_surfaces(gm_client, roster):
    """Unequipping the brooch removes both the force resistance and the
    magic-missile immunity. Restores the original inventory on teardown."""
    krieger = roster["Krieger Stonefist"]
    data = await _sheet_json(gm_client, krieger["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    idx = _brooch_index(data)
    assert idx is not None, "Krieger has no Brooch of Shielding item"
    try:
        inv[idx] = {**inv[idx], "equipped": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-fields",
            json={"inventory": inv},
        )
        data2 = await _sheet_json(gm_client, krieger["id"])
        derived2 = data2.get("derived") or {}
        force_resisted = "force" in (
            (derived2.get("resistances") or {}).get("types") or []
        )
        assert not force_resisted, (
            f"expected no force resistance after unequip, got: "
            f"{derived2.get('resistances')!r}"
        )
        assert "magic_missile_immune" not in derived2, (
            f"expected no magic_missile_immune after unequip, got: "
            f"{derived2.get('magic_missile_immune')!r}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-fields",
            json={"inventory": snapshot},
        )
