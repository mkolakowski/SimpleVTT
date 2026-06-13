"""v2.185.1 — in-battle proof that the self-buff potions
(`_use_item_action_self_buff_potion`, v2.184.0 / v2.185.0) actually
install their buff on the drinker's combatant.

The existing per-potion tests only assert `buff_installed` is a *bool*
because `_install_buff` is best-effort — it silently no-ops when the
drinker isn't in an active battle (the buff engine operates on
combatants, not on bare sheets). This file closes that gap: it puts
Garrik in an active battle FIRST, then drinks each potion and asserts
(a) the response reports `buff_installed: True` and (b) the buff key
actually shows up in `GET /character/{id}/buffs`.

Garrik carries both a Potion of Speed (→ haste) and a Potion of
Heroism (→ bless). Each fixture snapshots + restores his inventory so
the consume doesn't deplete the seed across re-runs. The battle is torn
down in teardown so it doesn't leak into other tests.
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


async def _buff_keys(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    assert r.status_code == 200, r.text
    return {(b or {}).get("key") for b in (r.json().get("buffs") or [])}


@pytest_asyncio.fixture
async def garrik_in_battle(gm_client, roster):
    """Put Garrik in an active solo battle; snapshot his inventory and
    restore it + clear the battle in teardown."""
    garrik = roster["Garrik Ironside"]
    sheet = await _sheet(gm_client, garrik["id"])
    inventory = list(sheet.get("inventory") or [])
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [{
                "id": f"tok_selfbuff_garrik_{garrik['id']}",
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


async def test_potion_of_speed_installs_haste_in_battle(
    gm_client, garrik_in_battle,
):
    """In an active battle, drinking Speed reports buff_installed True
    and the haste buff actually lands on Garrik's combatant."""
    garrik = garrik_in_battle["char"]
    idx = _slug_index(garrik_in_battle["inventory"], "potion-of-speed")
    assert idx >= 0, "Garrik must carry a seeded Potion of Speed"

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/use_item_action",
        json={"inventory_index": idx, "action_key": "drink"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["buff_key"] == "haste"
    assert body["buff_installed"] is True
    assert body["consumed"] is True

    assert "haste" in await _buff_keys(gm_client, garrik["id"])


async def test_potion_of_heroism_installs_bless_in_battle(
    gm_client, garrik_in_battle,
):
    """In an active battle, drinking Heroism reports buff_installed True
    and the bless buff actually lands on Garrik's combatant."""
    garrik = garrik_in_battle["char"]
    idx = _slug_index(garrik_in_battle["inventory"], "potion-of-heroism")
    assert idx >= 0, "Garrik must carry a seeded Potion of Heroism"

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/use_item_action",
        json={"inventory_index": idx, "action_key": "drink"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["buff_key"] == "bless"
    assert body["buff_installed"] is True
    assert body["temp_hp_granted"] == 10

    assert "bless" in await _buff_keys(gm_client, garrik["id"])
