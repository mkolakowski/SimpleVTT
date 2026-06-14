"""v2.279.0 — Dragon Scale Mail (RAW DMG p.165, very rare, attunement):
while worn, +1 AC, advantage on saves vs. dragon Frightful Presence /
breath weapons, AND resistance to one damage type keyed to the dragon's
color (Blue → lightning, Red → fire, White → cold, etc.).

The resisted type rides the inventory item via the per-item
`_resistance_type` rider on the shared `dragon-scale-mail` slug — the same
pattern as Ring of Resistance and the Ioun Stone variants. It folds into the
aggregated `resistance_to` list that `_resistance_halve` consults in the live
damage pipeline, and surfaces on `/sheet-json` as
`derived.resistances = {types, sources}`. The +1 AC half is descriptive in
v1 (armor AC isn't surfaced on /sheet-json yet).

Demo fixture: Garrik Ironside (Fighter) carries a Dragon Scale Mail (Blue,
`_resistance_type: "lightning"`) as inert spare loot (equipped=False /
attuned=False) so it adds zero resistance to his baseline and leaves his
belt / luckstone tests untouched. The tests PATCH it equipped+attuned, read
the lightning `derived.resistances`, then restore the seed inventory (and HP for
the damage-pipeline tests).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_ARMOR_SLUG = "dragon-scale-mail"


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest_asyncio.fixture
async def garrik(roster):
    return roster["Garrik Ironside"]


async def _equip_armor_and_read(gm_client, char_id):
    """PATCH the spare Dragon Scale Mail ON (equipped + attuned), read
    /sheet-json, then restore the original inventory. Returns the post-equip
    derived block."""
    data = await _sheet_json(gm_client, char_id)
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    new_inv = [dict(it) if isinstance(it, dict) else it for it in inv]
    found = False
    for it in new_inv:
        if isinstance(it, dict) and it.get("_slug") == _ARMOR_SLUG:
            it["equipped"], it["attuned"] = True, True
            found = True
    assert found, "Garrik has no dragon-scale-mail item"
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


async def _equip_then_deal_damage(gm_client, char_id, amount, dtype):
    """Equip the armor, apply typed damage through the resistance pipeline,
    return (before, after) HP. Restores the seed inventory AND HP."""
    data = await _sheet_json(gm_client, char_id)
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    hp = dict((data.get("sheet") or {}).get("hp") or {})
    new_inv = [dict(it) if isinstance(it, dict) else it for it in inv]
    for it in new_inv:
        if isinstance(it, dict) and it.get("_slug") == _ARMOR_SLUG:
            it["equipped"], it["attuned"] = True, True
    try:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
            json={"inventory": new_inv},
        )
        before = int(hp.get("current") or 0)
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
            json={
                "hp": {"current": before - amount},
                "hp_change_reason": "damage",
                "damage_amount": amount,
                "damage_type": dtype,
            },
        )
        data2 = await _sheet_json(gm_client, char_id)
        after = int(((data2.get("sheet") or {}).get("hp") or {}).get("current") or 0)
        return before, after
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
            json={"inventory": snapshot, "hp": hp},
        )


async def test_dragon_scale_mail_exposes_lightning_resistance(gm_client, garrik):
    """Happy path: equipping the Blue Dragon Scale Mail surfaces lightning in
    `derived.resistances`, with the armor named in its sources."""
    derived = await _equip_armor_and_read(gm_client, garrik["id"])
    res = derived.get("resistances") or {}
    assert "lightning" in (res.get("types") or []), (
        f"expected lightning in resistances, got: {res!r}"
    )
    assert any(
        "Dragon Scale Mail" in str(s) for s in res.get("sources") or []
    ), f"expected the armor named in resistance sources, got: {res!r}"


async def test_dragon_scale_mail_baseline_has_no_lightning_resistance(gm_client, garrik):
    """Control: with the armor inert (seed state), Garrik has no lightning
    resistance — proving the resistance is item-sourced, not baked in. (His
    Frost Brand grants FIRE resistance, which is why Blue/lightning scales
    were chosen for the demo fixture.)"""
    data = await _sheet_json(gm_client, garrik["id"])
    res = (data.get("derived") or {}).get("resistances") or {}
    assert "lightning" not in (res.get("types") or []), (
        f"unexpected baseline lightning resistance, got: {res!r}"
    )


async def test_dragon_scale_mail_halves_lightning_damage(gm_client, garrik):
    """End-to-end: 20 lightning damage to the wearer drops HP by only 10 — the
    equipped armor halves it through `_resistance_halve`."""
    before, after = await _equip_then_deal_damage(gm_client, garrik["id"], 20, "lightning")
    assert after == before - 10, (
        f"lightning damage not halved by the armor: {before} → {after} (expected -10)"
    )


async def test_dragon_scale_mail_does_not_halve_other_types(gm_client, garrik):
    """Control: 20 COLD damage is unaffected by Blue (lightning) scales — full
    20 applies, proving the resistance is the color-keyed type only."""
    before, after = await _equip_then_deal_damage(gm_client, garrik["id"], 20, "cold")
    assert after == before - 20, (
        f"cold damage wrongly reduced: {before} → {after} (expected -20)"
    )
