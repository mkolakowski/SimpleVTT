"""v2.279.0 — Cloak of Arachnida (RAW DMG p.158, very rare, attunement):
while worn, you have resistance to poison damage AND a climbing speed equal
to your walking speed (move across vertical surfaces / ceilings hands-free).

Two existing substrates compose in one passive payload:
  - the poison `resistance_to` folds into the aggregated `resistance_to`
    list that `_resistance_halve` consults in the live damage pipeline
    (same as Ring of Resistance) — surfaced on `/sheet-json` as
    `derived.resistances = {types, sources}`;
  - `spider_climb` surfaces on `/sheet-json` as
    `derived.spider_climb = {sources}` (same as Slippers of Spider Climbing).

Demo fixture: Lyra Sunstrider (Bard) carries the cloak as inert spare loot
(equipped=False / attuned=False) — she's already at the RAW 3-item attunement
cap and wears a Cloak of Displacement. The tests PATCH it equipped+attuned,
read the derived block, then restore the seed inventory (and HP for the
damage-pipeline test) so nothing leaks into other tests.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_CLOAK_SLUG = "cloak-of-arachnida"


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest_asyncio.fixture
async def lyra(roster):
    return roster["Lyra Sunstrider"]


async def _equip_cloak_and_read(gm_client, char_id):
    """PATCH the spare Cloak of Arachnida ON (equipped + attuned), read
    /sheet-json, then restore the original inventory. Returns the post-equip
    derived block."""
    data = await _sheet_json(gm_client, char_id)
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    new_inv = [dict(it) if isinstance(it, dict) else it for it in inv]
    found = False
    for it in new_inv:
        if isinstance(it, dict) and it.get("_slug") == _CLOAK_SLUG:
            it["equipped"], it["attuned"] = True, True
            found = True
    assert found, "Lyra has no cloak-of-arachnida item"
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"inventory": new_inv},
    )
    try:
        data2 = await _sheet_json(gm_client, char_id)
        return data2.get("derived") or {}
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
            json={"inventory": snapshot},
        )


async def test_cloak_exposes_poison_resistance_and_spider_climb(gm_client, lyra):
    """Happy path: equipping the cloak surfaces poison in
    `derived.resistances` AND `derived.spider_climb`, both naming the cloak."""
    derived = await _equip_cloak_and_read(gm_client, lyra["id"])
    res = derived.get("resistances") or {}
    assert "poison" in (res.get("types") or []), (
        f"expected poison in resistances, got: {res!r}"
    )
    assert any(
        "Cloak of Arachnida" in str(s) for s in res.get("sources") or []
    ), f"expected the cloak named in resistance sources, got: {res!r}"
    sc = derived.get("spider_climb") or {}
    assert any(
        "Cloak of Arachnida" in str(s) for s in sc.get("sources") or []
    ), f"expected the cloak named in spider_climb sources, got: {sc!r}"


async def test_cloak_unequipped_baseline_has_no_poison_resistance(gm_client, lyra):
    """Control: with the cloak inert (seed state), the cloak contributes no
    poison resistance and no spider_climb — Lyra has no other source of
    either, so both are absent from `derived`."""
    data = await _sheet_json(gm_client, lyra["id"])
    derived = data.get("derived") or {}
    res = derived.get("resistances") or {}
    assert "poison" not in (res.get("types") or []), (
        f"unexpected baseline poison resistance, got: {res!r}"
    )
    assert not derived.get("spider_climb"), (
        f"unexpected baseline spider_climb, got: {derived.get('spider_climb')!r}"
    )


async def test_cloak_halves_poison_damage(gm_client, lyra):
    """End-to-end: 20 poison damage to the cloak-wearer drops HP by only 10
    — the equipped cloak halves it through `_resistance_halve`. Restores the
    seed inventory AND HP on teardown."""
    data = await _sheet_json(gm_client, lyra["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    hp = dict((data.get("sheet") or {}).get("hp") or {})
    new_inv = [dict(it) if isinstance(it, dict) else it for it in inv]
    for it in new_inv:
        if isinstance(it, dict) and it.get("_slug") == _CLOAK_SLUG:
            it["equipped"], it["attuned"] = True, True
    try:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/sheet-fields",
            json={"inventory": new_inv},
        )
        before = int(hp.get("current") or 0)
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/sheet-fields",
            json={
                "hp": {"current": before - 20},
                "hp_change_reason": "damage",
                "damage_amount": 20,
                "damage_type": "poison",
            },
        )
        data2 = await _sheet_json(gm_client, lyra["id"])
        after = int(((data2.get("sheet") or {}).get("hp") or {}).get("current") or 0)
        assert after == before - 10, (
            f"poison damage not halved by the cloak: {before} → {after} "
            "(expected -10)"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/sheet-fields",
            json={"inventory": snapshot, "hp": hp},
        )
