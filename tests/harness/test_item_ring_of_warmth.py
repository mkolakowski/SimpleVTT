"""v2.246.0 — Ring of Warmth (RAW DMG p.193, uncommon, attunement): while
worn you have resistance to cold damage, and you (plus everything you wear
and carry) are unharmed by temperatures as low as -50 degrees Fahrenheit.

Two surfaces, both attunement-gated:
  - The cold *resistance* is a REAL mechanical effect — the catalog payload's
    `resistance_to: ["cold"]` folds into the aggregated `resistance_to` list
    that `_resistance_halve` consults in the live damage pipeline (the same
    surface the Ring of Resistance exercises), so cold damage to the wearer is
    halved through `PATCH .../sheet-fields`. It also surfaces on `/sheet-json`
    as `derived.resistances = {types, sources}`.
  - The -50°F environmental tolerance is GM-narrated in v1, surfaced via the
    boolean `cold_tolerance` flag as `derived.cold_tolerance = {sources}`.

Demo fixture: Brakka Wildmane (Path of the Beast Barbarian) wears it as her
3rd attuned item (Belt of Giant Strength + Ring of Free Action + this, RAW
max 3) — homed by detuning her redundant Ioun Stone of Constitution (kept
equipped) in the demo seed.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_RING_SLUG = "ring-of-warmth"


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _ring_index(data):
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    return next(
        (i for i, it in enumerate(inv)
         if isinstance(it, dict) and it.get("_slug") == _RING_SLUG),
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
async def brakka_hp_restore(gm_client, roster):
    """Snapshot Brakka's HP and restore it after the test so the typed-damage
    PATCHes don't leak into other tests."""
    brakka = roster["Brakka Wildmane"]
    data = await _sheet_json(gm_client, brakka["id"])
    hp = dict((data.get("sheet") or {}).get("hp") or {})
    try:
        yield brakka
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{brakka['id']}/sheet-fields",
            json={"hp": hp},
        )


async def test_ring_of_warmth_exposes_cold_resistance(gm_client, roster):
    """Happy path: Brakka's `/sheet-json` reports `derived.resistances`
    listing cold and `derived.cold_tolerance`, both naming the ring."""
    brakka = roster["Brakka Wildmane"]
    data = await _sheet_json(gm_client, brakka["id"])
    derived = data.get("derived") or {}
    res = derived.get("resistances")
    assert res is not None, f"expected derived.resistances, got: {derived!r}"
    assert "cold" in (res.get("types") or []), res
    assert any(
        "Ring of Warmth" in str(s) for s in res.get("sources") or []
    ), f"expected the ring named in resistance sources, got: {res!r}"
    tol = derived.get("cold_tolerance")
    assert tol is not None, f"expected derived.cold_tolerance, got: {derived!r}"
    assert any(
        "Ring of Warmth" in str(s) for s in tol.get("sources") or []
    ), f"expected the ring named in cold_tolerance sources, got: {tol!r}"


async def test_ring_of_warmth_halves_cold_damage(gm_client, brakka_hp_restore):
    """End-to-end: 20 cold damage to the cold-resisted wearer drops HP by
    only 10 — the equipped + attuned ring halves it through
    `_resistance_halve`."""
    brakka = brakka_hp_restore
    before = await _hp_current(gm_client, brakka["id"])
    await _deal_damage(gm_client, brakka["id"], before - 20, 20, "cold")
    after = await _hp_current(gm_client, brakka["id"])
    assert after == before - 10, (
        f"cold damage not halved by the ring: {before} → {after} (expected -10)"
    )


async def test_ring_of_warmth_does_not_halve_other_types(
    gm_client, brakka_hp_restore
):
    """Control: 20 FIRE damage is unaffected by the cold-resistance ring —
    full 20 applies, proving the resistance is type-specific."""
    brakka = brakka_hp_restore
    before = await _hp_current(gm_client, brakka["id"])
    await _deal_damage(gm_client, brakka["id"], before - 20, 20, "fire")
    after = await _hp_current(gm_client, brakka["id"])
    assert after == before - 20, (
        f"fire damage wrongly reduced: {before} → {after} (expected -20)"
    )


async def test_ring_of_warmth_requires_attunement(gm_client, roster):
    """Attunement-gated. Detuning the ring via `/attune` drops both
    `derived.resistances` (cold) and `derived.cold_tolerance`. Restores the
    seed attunement on teardown."""
    brakka = roster["Brakka Wildmane"]
    data = await _sheet_json(gm_client, brakka["id"])
    idx = _ring_index(data)
    assert idx is not None, "Brakka has no Ring of Warmth item"
    try:
        detune = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{brakka['id']}/attune",
            json={"inventory_index": idx, "attuned": False},
        )
        assert detune.status_code == 200, detune.text
        data2 = await _sheet_json(gm_client, brakka["id"])
        derived2 = data2.get("derived") or {}
        cold_resisted = "cold" in (
            (derived2.get("resistances") or {}).get("types") or []
        )
        assert not cold_resisted, (
            f"expected no cold resistance once detuned, got: "
            f"{derived2.get('resistances')!r}"
        )
        assert "cold_tolerance" not in derived2, (
            f"expected no cold_tolerance once detuned, got: {derived2!r}"
        )
    finally:
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{brakka['id']}/attune",
            json={"inventory_index": idx, "attuned": True},
        )


async def test_ring_of_warmth_unequip_drops_flags(gm_client, roster):
    """Unequipping the ring removes both derived surfaces. Restores the
    original inventory on teardown."""
    brakka = roster["Brakka Wildmane"]
    data = await _sheet_json(gm_client, brakka["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    idx = _ring_index(data)
    assert idx is not None, "Brakka has no Ring of Warmth item"
    try:
        inv[idx] = {**inv[idx], "equipped": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{brakka['id']}/sheet-fields",
            json={"inventory": inv},
        )
        data2 = await _sheet_json(gm_client, brakka["id"])
        derived2 = data2.get("derived") or {}
        cold_resisted = "cold" in (
            (derived2.get("resistances") or {}).get("types") or []
        )
        assert not cold_resisted, (
            f"expected no cold resistance after unequip, got: "
            f"{derived2.get('resistances')!r}"
        )
        assert "cold_tolerance" not in derived2, (
            f"expected no cold_tolerance after unequip, got: {derived2!r}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{brakka['id']}/sheet-fields",
            json={"inventory": snapshot},
        )
