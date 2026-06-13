"""v2.188.0 — drink-time damage-type pick for a GENERIC Potion of
Resistance. RAW (DMG p.188) the drinker chooses the damage type, so a
potion seeded WITHOUT a `resistance_type` accepts a `resistance_type`
override in the `/use_item_action` request body. The handler resolves
that override to the matching `resistance-<type>` template — proving the
type is chosen at drink-time, not baked into the seed.

Garrik carries a generic "Potion of Resistance" (no seeded type)
alongside his pre-typed fire + cold instances. This test drinks it in an
active battle with `resistance_type: "lightning"` and proves the live
damage pipeline halves LIGHTNING (20 → 10) but not FIRE (20 → 20).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _sheet(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    return (r.json() or {}).get("sheet") or {}


def _generic_potion_index(inventory):
    """The untyped instance: slug matches but NO `resistance_type`."""
    for i, it in enumerate(inventory):
        if not isinstance(it, dict):
            continue
        if (it.get("_slug") or "") == "potion-of-resistance" and not (
            it.get("resistance_type")
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
async def garrik_drank_generic_lightning(gm_client, roster):
    """Put Garrik in an active battle and drink the GENERIC Potion of
    Resistance, choosing lightning at drink-time. Asserts the resolved
    buff is the lightning template. Restores inventory + clears battle
    in teardown."""
    garrik = roster["Garrik Ironside"]
    sheet = await _sheet(gm_client, garrik["id"])
    inventory = list(sheet.get("inventory") or [])
    idx = _generic_potion_index(inventory)
    assert idx >= 0, "Garrik must carry a generic (untyped) Potion of Resistance"

    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [{
                "id": f"tok_genres_garrik_{garrik['id']}",
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
        json={"inventory_index": idx, "action_key": "drink",
              "resistance_type": "lightning"},
    )
    assert drink.status_code == 200, drink.text
    body = drink.json()
    assert body["buff_installed"] is True
    assert body["buff_key"] == "resistance-lightning", body
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


async def test_chosen_lightning_is_halved(
    gm_client, garrik_drank_generic_lightning,
):
    """Drink-time pick = lightning → 20 lightning damage drops HP by 10."""
    garrik = garrik_drank_generic_lightning
    before = await _hp_current(gm_client, garrik["id"])
    await _deal_damage(gm_client, garrik["id"], before - 20, 20, "lightning")
    after = await _hp_current(gm_client, garrik["id"])
    assert after == before - 10, (
        f"lightning not halved: {before} → {after} (expected -10)"
    )


async def test_unchosen_fire_is_not_halved(
    gm_client, garrik_drank_generic_lightning,
):
    """Control: 20 fire is unaffected — the drink-time pick was lightning,
    not fire."""
    garrik = garrik_drank_generic_lightning
    before = await _hp_current(gm_client, garrik["id"])
    await _deal_damage(gm_client, garrik["id"], before - 20, 20, "fire")
    after = await _hp_current(gm_client, garrik["id"])
    assert after == before - 20, (
        f"fire wrongly reduced: {before} → {after} (expected -20)"
    )
