"""v2.201.0 — Potion of Flying (RAW DMG p.187, very rare): drink → a flying
speed equal to your walking speed for 1 hour, no concentration.

The tenth self-buff potion. Carries a real mechanical marker:
`effects.fly_speed_ft`, the same one the Stormborn/levitate/dragon-wings
flight buffs use to surface the flying capability for the UI/GM on the 2D
map. The contract worth proving is the install plus that the installed buff
actually carries the `fly_speed_ft` marker. Modeled at 30 ft (the default
PC walking speed); the falls-when-it-ends nuance is GM-narrated.

Mirrors `test_potion_of_invisibility.py` — `_install_buff` no-ops outside
combat, so the test puts Garrik in an active solo battle first.
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


async def _buffs(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    assert r.status_code == 200, r.text
    return r.json().get("buffs") or []


@pytest_asyncio.fixture
async def garrik_in_battle(gm_client, roster):
    garrik = roster["Garrik Ironside"]
    sheet = await _sheet(gm_client, garrik["id"])
    inventory = list(sheet.get("inventory") or [])
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [{
                "id": f"tok_fly_garrik_{garrik['id']}",
                "char_id": garrik["id"], "name": garrik["name"],
                "initiative": 15, "hp_current": 85, "hp_max": 85,
                "buffs": [],
                "economy": {"action": False, "bonus": False,
                            "reaction": False, "movement": 0},
            }],
            "turn_index": 0, "round": 1, "active": True,
        },
    )
    try:
        yield {"char": garrik, "inventory": inventory}
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


async def test_flying_installs_buff_with_fly_speed(
    gm_client, garrik_in_battle,
):
    """In an active battle, drinking Flying reports buff_installed True +
    consumed True, the `flying-potion` buff lands on Garrik's combatant,
    AND it carries the `effects.fly_speed_ft` marker the flight code reads."""
    garrik = garrik_in_battle["char"]
    idx = _slug_index(garrik_in_battle["inventory"], "potion-of-flying")
    assert idx >= 0, "Garrik must carry a seeded Potion of Flying"

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/use_item_action",
        json={"inventory_index": idx, "action_key": "drink"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["buff_key"] == "flying-potion", body
    assert body["buff_installed"] is True, body
    assert body["consumed"] is True, body

    buffs = await _buffs(gm_client, garrik["id"])
    fly = next(
        (b for b in buffs if (b or {}).get("key") == "flying-potion"),
        None,
    )
    assert fly is not None, buffs
    assert (fly.get("effects") or {}).get("fly_speed_ft", 0) > 0, fly


async def test_flying_bad_action_key_404(gm_client, garrik_in_battle):
    """A non-existent action_key on the potion → 404."""
    garrik = garrik_in_battle["char"]
    idx = _slug_index(garrik_in_battle["inventory"], "potion-of-flying")
    assert idx >= 0

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/use_item_action",
        json={"inventory_index": idx, "action_key": "soar"},
    )
    assert resp.status_code == 404, resp.text
