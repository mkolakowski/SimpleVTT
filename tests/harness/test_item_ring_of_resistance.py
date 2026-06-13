"""v2.235.0 — Ring of Resistance (RAW DMG p.192, rare, attunement): while
worn, you have resistance to one damage type (the gem indicates which).

Unlike the recent passive-flag items, this is a REAL mechanical effect: the
resisted type rides the inventory item via the per-item `_resistance_type`
rider on the shared `ring-of-resistance` slug, aggregates in
`_equipped_item_effects` (`resistance_to` list), and is consulted by
`_resistance_halve` in the live damage pipeline — so matching damage is
halved through `PATCH .../sheet-fields`. It also surfaces on `/sheet-json`
as `derived.resistances = {types, sources}`.

Demo fixture: Dame Seraphine Vael (Vengeance Paladin) wears a Ring of
Resistance (Fire) as her 3rd attuned item (Sun Blade + Periapt of Wound
Closure + this ring, RAW max 3). Fire damage to her is halved; cold is not
(type-specific, not a wildcard).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_RING_SLUG = "ring-of-resistance"


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
async def seraphine_hp_restore(gm_client, roster):
    """Snapshot Seraphine's HP and restore it after the test so the
    typed-damage PATCHes don't leak into other tests."""
    sera = roster["Dame Seraphine Vael"]
    data = await _sheet_json(gm_client, sera["id"])
    hp = dict((data.get("sheet") or {}).get("hp") or {})
    try:
        yield sera
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{sera['id']}/sheet-fields",
            json={"hp": hp},
        )


async def test_ring_exposes_resistances_on_sheet_json(gm_client, roster):
    """Happy path: Seraphine's `/sheet-json` reports `derived.resistances`
    listing fire, with the ring named in its sources."""
    sera = roster["Dame Seraphine Vael"]
    data = await _sheet_json(gm_client, sera["id"])
    res = (data.get("derived") or {}).get("resistances")
    assert res is not None, (
        f"expected derived.resistances, got: {data.get('derived')!r}"
    )
    assert "fire" in (res.get("types") or []), res
    assert any(
        "Ring of Resistance" in str(s) for s in res.get("sources") or []
    ), f"expected the ring named in sources, got: {res!r}"


async def test_ring_halves_matching_damage(gm_client, seraphine_hp_restore):
    """End-to-end: 20 fire damage to the fire-resisted wearer drops HP by
    only 10 — the equipped ring halves it through `_resistance_halve`."""
    sera = seraphine_hp_restore
    before = await _hp_current(gm_client, sera["id"])
    await _deal_damage(gm_client, sera["id"], before - 20, 20, "fire")
    after = await _hp_current(gm_client, sera["id"])
    assert after == before - 10, (
        f"fire damage not halved by the ring: {before} → {after} (expected -10)"
    )


async def test_ring_does_not_halve_other_types(gm_client, seraphine_hp_restore):
    """Control: 20 COLD damage is unaffected by a fire-resistance ring —
    full 20 applies, proving the resistance is type-specific."""
    sera = seraphine_hp_restore
    before = await _hp_current(gm_client, sera["id"])
    await _deal_damage(gm_client, sera["id"], before - 20, 20, "cold")
    after = await _hp_current(gm_client, sera["id"])
    assert after == before - 20, (
        f"cold damage wrongly reduced: {before} → {after} (expected -20)"
    )
