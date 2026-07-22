"""v2.187.0 — proof that the Potion of Resistance is now type-aware: the
RAW GM-chosen damage type is carried on the inventory item
(`resistance_type`) and the self-buff handler maps it to the matching
`resistance-<type>` template (one of the ten RAW damage types) rather
than the v2.186.0 hardcoded fire instance.

Garrik now carries a SECOND typed potion — Potion of Cold Resistance
(`resistance_type: "cold"`). This test drinks it in an active battle and
proves the live damage pipeline halves COLD (20 → 10) but NOT FIRE
(20 → 20), the mirror image of the fire test in
`test_potion_of_resistance_damage_halving.py`. Together the two files
prove the type-pick actually selects the buffed type.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _sheet(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    return (r.json() or {}).get("sheet") or {}


def _cold_potion_index(inventory):
    for i, it in enumerate(inventory):
        if not isinstance(it, dict):
            continue
        if (it.get("_slug") or "") == "potion-of-resistance" and (
            it.get("resistance_type") == "cold"
        ):
            return i
    return -1


async def _hp_current(gm_client, char_id):
    sheet = await _sheet(gm_client, char_id)
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
async def garrik_drank_cold_resistance(gm_client, roster):
    """Put Garrik in an active battle and have him drink the Potion of
    Cold Resistance (the second typed instance). Asserts the resolved
    buff is the cold template. Restores inventory + clears battle in
    teardown."""
    garrik = roster["Garrik Ironside"]
    sheet = await _sheet(gm_client, garrik["id"])
    inventory = list(sheet.get("inventory") or [])
    idx = _cold_potion_index(inventory)
    assert idx >= 0, "Garrik must carry a seeded Potion of Cold Resistance"

    # B18 class 6: Garrik is the demo's item-showcase PC — his seeded
    # equipped Frost Brand Longsword grants innate fire resistance, which
    # would make the "fire not halved" control fail. Un-equip everything so
    # the ONLY resistance in play is the potion the test drinks; the finally
    # block restores the original inventory.
    clean_inv = [{**it, "equipped": False} for it in inventory]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/sheet-fields",
        json={"inventory": clean_inv},
    )

    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [{
                "id": f"tok_coldres_garrik_{garrik['id']}",
                "char_id": garrik["id"], "name": garrik["name"],
                "initiative": 15, "hp_current": 85, "hp_max": 85,
                "buffs": [],
                "economy": {"action": False, "bonus": False,
                            "reaction": False, "movement": 0},
            }],
            "turn_index": 0, "round": 1, "active": True,
        },
    )
    drink = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/use_item_action",
        json={"inventory_index": idx, "action_key": "drink"},
    )
    assert drink.status_code == 200, drink.text
    body = drink.json()
    assert body["buff_installed"] is True
    assert body["buff_key"] == "resistance-cold", body
    assert body["item_name"] == "Potion of Cold Resistance", body
    try:
        yield garrik
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/sheet-fields",
            json={"inventory": inventory},
        )
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={"combatants": [], "turn_index": 0, "round": 1,
                  "active": False},
        )


async def test_cold_damage_is_halved(gm_client, garrik_drank_cold_resistance):
    """20 cold damage to the cold-resisted drinker drops HP by 10."""
    garrik = garrik_drank_cold_resistance
    before = await _hp_current(gm_client, garrik["id"])
    await _deal_damage(gm_client, garrik["id"], before - 20, 20, "cold")
    after = await _hp_current(gm_client, garrik["id"])
    assert after == before - 10, (
        f"cold damage not halved: {before} → {after} (expected -10)"
    )


async def test_fire_damage_is_not_halved(gm_client, garrik_drank_cold_resistance):
    """Control: 20 FIRE damage is unaffected by COLD resistance — full
    20 applies, proving the type-pick selected cold (not fire)."""
    garrik = garrik_drank_cold_resistance
    before = await _hp_current(gm_client, garrik["id"])
    await _deal_damage(gm_client, garrik["id"], before - 20, 20, "fire")
    after = await _hp_current(gm_client, garrik["id"])
    assert after == before - 20, (
        f"fire damage wrongly reduced: {before} → {after} (expected -20)"
    )
