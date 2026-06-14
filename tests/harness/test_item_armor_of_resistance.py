"""v2.248.0 — Armor of Resistance (RAW DMG p.152, rare, attunement): "you
have resistance to one type of damage while you wear this armor."

This is a pure substrate reuse of the v2.235.0 Ring of Resistance surface —
the only engine change is a new `armor-of-resistance` catalog entry. Like the
ring, each physical suit is a fixed damage type, so the resisted type rides the
inventory item via the per-item `_resistance_type` rider (here "acid") on the
shared `armor-of-resistance` slug. The walker folds it into the aggregated
`resistance_to` list that `_resistance_halve` consults in the live damage
pipeline, so acid damage to the wearer is halved through
`PATCH .../sheet-fields`. It surfaces on `/sheet-json` as
`derived.resistances = {types, sources}`. Attunement-gated.

Demo fixture: Sir Caelan Lightbringer (Paladin) wears Armor of Resistance
(Acid) as his 3rd attuned item (Ioun Stone of Reserve + Ring of Feather
Falling + this, RAW max 3) — homed by detuning his redundant Ioun Stone of
Dexterity (kept equipped; heavy armor meant the DEX bump never touched AC).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_ARMOR_SLUG = "armor-of-resistance"


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _armor_index(data):
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    return next(
        (i for i, it in enumerate(inv)
         if isinstance(it, dict) and it.get("_slug") == _ARMOR_SLUG),
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
async def caelan_hp_restore(gm_client, roster):
    """Snapshot Caelan's HP and restore it after the test so the typed-damage
    PATCHes don't leak into other tests."""
    caelan = roster["Sir Caelan Lightbringer"]
    data = await _sheet_json(gm_client, caelan["id"])
    hp = dict((data.get("sheet") or {}).get("hp") or {})
    try:
        yield caelan
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/sheet-fields",
            json={"hp": hp},
        )


async def test_armor_exposes_acid_resistance(gm_client, roster):
    """Happy path: Caelan's `/sheet-json` reports `derived.resistances` listing
    acid, naming the armor in its sources."""
    caelan = roster["Sir Caelan Lightbringer"]
    data = await _sheet_json(gm_client, caelan["id"])
    derived = data.get("derived") or {}
    res = derived.get("resistances")
    assert res is not None, f"expected derived.resistances, got: {derived!r}"
    assert "acid" in (res.get("types") or []), res
    assert any(
        "Armor of Resistance" in str(s) for s in res.get("sources") or []
    ), f"expected the armor named in resistance sources, got: {res!r}"


async def test_armor_halves_acid_damage(gm_client, caelan_hp_restore):
    """End-to-end: 20 acid damage to the acid-resisted wearer drops HP by only
    10 — the equipped + attuned armor halves it through `_resistance_halve`."""
    caelan = caelan_hp_restore
    before = await _hp_current(gm_client, caelan["id"])
    await _deal_damage(gm_client, caelan["id"], before - 20, 20, "acid")
    after = await _hp_current(gm_client, caelan["id"])
    assert after == before - 10, (
        f"acid damage not halved by the armor: {before} → {after} (expected -10)"
    )


async def test_armor_does_not_halve_other_types(gm_client, caelan_hp_restore):
    """Control: 20 FIRE damage is unaffected by the acid-resistance armor —
    full 20 applies, proving the resistance is type-specific."""
    caelan = caelan_hp_restore
    before = await _hp_current(gm_client, caelan["id"])
    await _deal_damage(gm_client, caelan["id"], before - 20, 20, "fire")
    after = await _hp_current(gm_client, caelan["id"])
    assert after == before - 20, (
        f"fire damage wrongly reduced: {before} → {after} (expected -20)"
    )


async def test_armor_requires_attunement(gm_client, roster):
    """Attunement-gated. Detuning the armor via `/attune` drops the acid entry
    from `derived.resistances`. Restores the seed attunement on teardown."""
    caelan = roster["Sir Caelan Lightbringer"]
    data = await _sheet_json(gm_client, caelan["id"])
    idx = _armor_index(data)
    assert idx is not None, "Caelan has no Armor of Resistance item"
    try:
        detune = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/attune",
            json={"inventory_index": idx, "attuned": False},
        )
        assert detune.status_code == 200, detune.text
        data2 = await _sheet_json(gm_client, caelan["id"])
        derived2 = data2.get("derived") or {}
        acid_resisted = "acid" in (
            (derived2.get("resistances") or {}).get("types") or []
        )
        assert not acid_resisted, (
            f"expected no acid resistance once detuned, got: "
            f"{derived2.get('resistances')!r}"
        )
    finally:
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/attune",
            json={"inventory_index": idx, "attuned": True},
        )


async def test_armor_unequip_drops_resistance(gm_client, roster):
    """Unequipping the armor removes the acid resistance. Restores the original
    inventory on teardown."""
    caelan = roster["Sir Caelan Lightbringer"]
    data = await _sheet_json(gm_client, caelan["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    idx = _armor_index(data)
    assert idx is not None, "Caelan has no Armor of Resistance item"
    try:
        inv[idx] = {**inv[idx], "equipped": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/sheet-fields",
            json={"inventory": inv},
        )
        data2 = await _sheet_json(gm_client, caelan["id"])
        derived2 = data2.get("derived") or {}
        acid_resisted = "acid" in (
            (derived2.get("resistances") or {}).get("types") or []
        )
        assert not acid_resisted, (
            f"expected no acid resistance after unequip, got: "
            f"{derived2.get('resistances')!r}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/sheet-fields",
            json={"inventory": snapshot},
        )
