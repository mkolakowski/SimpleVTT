"""v2.247.0 — Boots of the Winterlands (RAW DMG p.156, uncommon, attunement):
resistance to cold damage, ignore difficult terrain from ice/snow, and
tolerance of cold environments down to -50F (-100 in heavy clothing).

This reuses the v2.246.0 Ring of Warmth cold substrate VERBATIM (zero new
engine code) — the only change is a new `boots-of-the-winterlands` catalog
entry. Two surfaces, both attunement-gated:
  - The cold *resistance* rides the catalog payload's `resistance_to: ["cold"]`,
    folding into the aggregated `resistance_to` list that `_resistance_halve`
    consults in the live damage pipeline, so cold damage to the wearer is
    halved through `PATCH .../sheet-fields`. It surfaces on `/sheet-json` as
    `derived.resistances = {types, sources}`.
  - The -50F environmental tolerance surfaces via the boolean `cold_tolerance`
    flag as `derived.cold_tolerance = {sources}`.
The ignore-ice/snow-difficult-terrain rider is GM-narrated in v1.

Demo fixture: Rowan Quickbow (Ranger) wears them as his 3rd attuned item
(Gauntlets of Ogre Power + Ioun Stone of Sustenance + these, RAW max 3) —
homed by detuning his redundant Ioun Stone of Charisma (kept equipped).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_BOOTS_SLUG = "boots-of-the-winterlands"


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _boots_index(data):
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    return next(
        (i for i, it in enumerate(inv)
         if isinstance(it, dict) and it.get("_slug") == _BOOTS_SLUG),
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
async def rowan_hp_restore(gm_client, roster):
    """Snapshot Rowan's HP and restore it after the test so the typed-damage
    PATCHes don't leak into other tests."""
    rowan = roster["Rowan Quickbow"]
    data = await _sheet_json(gm_client, rowan["id"])
    hp = dict((data.get("sheet") or {}).get("hp") or {})
    try:
        yield rowan
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/sheet-fields",
            json={"hp": hp},
        )


async def test_boots_expose_cold_resistance(gm_client, roster):
    """Happy path: Rowan's `/sheet-json` reports `derived.resistances` listing
    cold and `derived.cold_tolerance`, both naming the boots."""
    rowan = roster["Rowan Quickbow"]
    data = await _sheet_json(gm_client, rowan["id"])
    derived = data.get("derived") or {}
    res = derived.get("resistances")
    assert res is not None, f"expected derived.resistances, got: {derived!r}"
    assert "cold" in (res.get("types") or []), res
    assert any(
        "Boots of the Winterlands" in str(s) for s in res.get("sources") or []
    ), f"expected the boots named in resistance sources, got: {res!r}"
    tol = derived.get("cold_tolerance")
    assert tol is not None, f"expected derived.cold_tolerance, got: {derived!r}"
    assert any(
        "Boots of the Winterlands" in str(s) for s in tol.get("sources") or []
    ), f"expected the boots named in cold_tolerance sources, got: {tol!r}"


async def test_boots_halve_cold_damage(gm_client, rowan_hp_restore):
    """End-to-end: 20 cold damage to the cold-resisted wearer drops HP by
    only 10 — the equipped + attuned boots halve it through
    `_resistance_halve`."""
    rowan = rowan_hp_restore
    before = await _hp_current(gm_client, rowan["id"])
    await _deal_damage(gm_client, rowan["id"], before - 20, 20, "cold")
    after = await _hp_current(gm_client, rowan["id"])
    assert after == before - 10, (
        f"cold damage not halved by the boots: {before} → {after} (expected -10)"
    )


async def test_boots_do_not_halve_other_types(gm_client, rowan_hp_restore):
    """Control: 20 FIRE damage is unaffected by the cold-resistance boots —
    full 20 applies, proving the resistance is type-specific."""
    rowan = rowan_hp_restore
    before = await _hp_current(gm_client, rowan["id"])
    await _deal_damage(gm_client, rowan["id"], before - 20, 20, "fire")
    after = await _hp_current(gm_client, rowan["id"])
    assert after == before - 20, (
        f"fire damage wrongly reduced: {before} → {after} (expected -20)"
    )


async def test_boots_require_attunement(gm_client, roster):
    """Attunement-gated. Detuning the boots via `/attune` drops both
    `derived.resistances` (cold) and `derived.cold_tolerance`. Restores the
    seed attunement on teardown."""
    rowan = roster["Rowan Quickbow"]
    data = await _sheet_json(gm_client, rowan["id"])
    idx = _boots_index(data)
    assert idx is not None, "Rowan has no Boots of the Winterlands item"
    try:
        detune = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/attune",
            json={"inventory_index": idx, "attuned": False},
        )
        assert detune.status_code == 200, detune.text
        data2 = await _sheet_json(gm_client, rowan["id"])
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
            f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/attune",
            json={"inventory_index": idx, "attuned": True},
        )


async def test_boots_unequip_drops_flags(gm_client, roster):
    """Unequipping the boots removes both derived surfaces. Restores the
    original inventory on teardown."""
    rowan = roster["Rowan Quickbow"]
    data = await _sheet_json(gm_client, rowan["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    idx = _boots_index(data)
    assert idx is not None, "Rowan has no Boots of the Winterlands item"
    try:
        inv[idx] = {**inv[idx], "equipped": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/sheet-fields",
            json={"inventory": inv},
        )
        data2 = await _sheet_json(gm_client, rowan["id"])
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
            f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/sheet-fields",
            json={"inventory": snapshot},
        )
