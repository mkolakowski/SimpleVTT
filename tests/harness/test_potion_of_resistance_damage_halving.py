"""v2.186.1 — end-to-end proof that the Potion of Fire Resistance buff
(v2.186.0) actually HALVES incoming fire damage through the live damage
pipeline, not just that the buff installs.

Chain exercised: drink the potion in an active battle
(`/use_item_action`) → `_install_buff` + `_mirror_buffs_to_sheet` write
the `resistance-fire` buff (with `effects.resistance_to: ["fire"]`) onto
Garrik's sheet `_buffs_active` → a typed-damage `PATCH .../sheet-fields`
runs `_resistance_halve`, which reads that mirror and halves matching
damage before HP application.

Two deterministic checks (no dice): fire damage is halved (20 → 10),
cold damage is NOT (20 → 20) — proving the resistance is type-specific
(the `fire` instance, not a `["all"]` wildcard).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _sheet(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    return (r.json() or {}).get("sheet") or {}


def _slug_index(inventory, slug):
    for i, it in enumerate(inventory):
        if isinstance(it, dict) and (it.get("_slug") or "") == slug:
            return i
    return -1


async def _hp_current(gm_client, char_id):
    sheet = await _sheet(gm_client, char_id)
    return int((sheet.get("hp") or {}).get("current") or 0)


async def _deal_damage(gm_client, char_id, naive_current, amount, dtype):
    """Apply `amount` of `dtype` damage via the typed-damage sheet-fields
    path. `naive_current` is the client's pre-resistance HP guess; the
    server recomputes from the actual current HP if resistance fires."""
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
async def garrik_drank_resistance(gm_client, roster):
    """Put Garrik in an active battle and have him drink the Potion of
    Fire Resistance (installs + mirrors the resistance-fire buff to his
    sheet). Snapshot inventory; restore it + clear the battle in
    teardown."""
    garrik = roster["Garrik Ironside"]
    sheet = await _sheet(gm_client, garrik["id"])
    inventory = list(sheet.get("inventory") or [])
    idx = _slug_index(inventory, "potion-of-resistance")
    assert idx >= 0, "Garrik must carry a seeded Potion of Resistance"

    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [{
                "id": f"tok_reshalve_garrik_{garrik['id']}",
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
    assert drink.json()["buff_installed"] is True
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


async def test_fire_damage_is_halved(gm_client, garrik_drank_resistance):
    """20 fire damage to the fire-resisted drinker drops HP by 10."""
    garrik = garrik_drank_resistance
    before = await _hp_current(gm_client, garrik["id"])
    await _deal_damage(gm_client, garrik["id"], before - 20, 20, "fire")
    after = await _hp_current(gm_client, garrik["id"])
    assert after == before - 10, (
        f"fire damage not halved: {before} → {after} (expected -10)"
    )


async def test_cold_damage_is_not_halved(gm_client, garrik_drank_resistance):
    """Control: 20 COLD damage is unaffected by fire resistance — full
    20 applies, proving the buff is type-specific (not a wildcard)."""
    garrik = garrik_drank_resistance
    before = await _hp_current(gm_client, garrik["id"])
    await _deal_damage(gm_client, garrik["id"], before - 20, 20, "cold")
    after = await _hp_current(gm_client, garrik["id"])
    assert after == before - 20, (
        f"cold damage wrongly reduced: {before} → {after} (expected -20)"
    )
