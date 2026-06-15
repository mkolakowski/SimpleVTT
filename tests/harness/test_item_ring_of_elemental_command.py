"""v2.305.0 — Ring of Elemental Command (Fire) (RAW DMG p.190, legendary,
attunement): linked to the Elemental Plane of Fire, it grants resistance to
fire damage the moment you attune (the Air/Earth/Water variants gate their
resistance behind slaying an elemental — only Fire is immediate).

Lands on the same `_resistance_type` substrate as Ring of Resistance
(v2.235.0) and Dragon Scale Mail (v2.279.0): the resisted type rides the
inventory item via the per-item `_resistance_type: "fire"` rider on the
shared `ring-of-elemental-command` slug, aggregates in
`_equipped_item_effects` (`resistance_to` list), and is consulted by
`_resistance_halve` in the live damage pipeline — so matching fire damage is
halved through `PATCH .../sheet-fields`. It also surfaces on `/sheet-json` as
`derived.resistances = {types, sources}`. Attunement-gated.

Carrier: Magnus Hexbinder (Fiend Warlock) holds the ring as inert spare loot
(unequipped/unattuned). His Bronze Dragonborn racial resistance is LIGHTNING,
not fire, so the inert baseline takes full fire damage — cleanly proving the
ring is the fire-resistance source. Tests PATCH it equipped+attuned, deal fire
damage, assert the halving, then restore both inventory and HP.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_RING_SLUG = "ring-of-elemental-command"


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _hp_current(gm_client, char_id):
    data = await _sheet_json(gm_client, char_id)
    sheet = data.get("sheet") or {}
    return int((sheet.get("hp") or {}).get("current") or 0)


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


async def _restore_inv(gm_client, char_id, snapshot):
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"inventory": snapshot},
    )


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
async def magnus_restore(gm_client, roster):
    """Snapshot Magnus's HP + inventory and restore both after the test so the
    PATCHes (typed damage + ring equip) don't leak into other tests."""
    magnus = roster["Magnus Hexbinder"]
    data = await _sheet_json(gm_client, magnus["id"])
    hp = dict((data.get("sheet") or {}).get("hp") or {})
    inv = await _snapshot_inv(gm_client, magnus["id"])
    try:
        yield magnus
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
            json={"inventory": inv, "hp": hp},
        )


async def test_ring_baseline_takes_full_fire_damage(gm_client, magnus_restore):
    """Control: with the ring inert (seed, equipped=False), 20 fire damage
    lands in full — proving Magnus has no fire-resistance baseline."""
    magnus = magnus_restore
    before = await _hp_current(gm_client, magnus["id"])
    await _deal_damage(gm_client, magnus["id"], before - 20, 20, "fire")
    after = await _hp_current(gm_client, magnus["id"])
    assert after == before - 20, (
        f"fire wrongly reduced at baseline: {before} → {after} (expected -20)"
    )


async def test_ring_halves_fire_damage_when_attuned(gm_client, magnus_restore):
    """End-to-end: equip+attune the ring, then 20 fire damage drops HP by only
    10 — `_resistance_halve` halves it via the ring's `_resistance_type`."""
    magnus = magnus_restore
    await _patch_item(
        gm_client, magnus["id"], _RING_SLUG, equipped=True, attuned=True)
    before = await _hp_current(gm_client, magnus["id"])
    await _deal_damage(gm_client, magnus["id"], before - 20, 20, "fire")
    after = await _hp_current(gm_client, magnus["id"])
    assert after == before - 10, (
        f"fire not halved by the attuned ring: {before} → {after} (expected -10)"
    )


async def test_ring_requires_attunement(gm_client, magnus_restore):
    """Attunement gate: equipped-but-un-attuned takes full fire damage;
    attuning then halves it."""
    magnus = magnus_restore
    # Equipped, NOT attuned — the attunement gate should suppress resistance.
    await _patch_item(
        gm_client, magnus["id"], _RING_SLUG, equipped=True, attuned=False)
    before = await _hp_current(gm_client, magnus["id"])
    await _deal_damage(gm_client, magnus["id"], before - 20, 20, "fire")
    after = await _hp_current(gm_client, magnus["id"])
    assert after == before - 20, (
        f"un-attuned ring wrongly halved fire: {before} → {after} (expected -20)"
    )


async def test_ring_exposes_resistances_on_sheet_json(gm_client, magnus_restore):
    """Equipped+attuned, `/sheet-json` reports `derived.resistances` listing
    fire with the ring named in sources."""
    magnus = magnus_restore
    await _patch_item(
        gm_client, magnus["id"], _RING_SLUG, equipped=True, attuned=True)
    data = await _sheet_json(gm_client, magnus["id"])
    res = (data.get("derived") or {}).get("resistances")
    assert res is not None, (
        f"expected derived.resistances, got: {data.get('derived')!r}"
    )
    assert "fire" in (res.get("types") or []), res
    assert any(
        "Ring of Elemental Command" in str(s) for s in res.get("sources") or []
    ), f"expected the ring named in sources, got: {res!r}"
