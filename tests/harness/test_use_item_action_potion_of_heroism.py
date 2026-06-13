"""v2.184.0 — magic-items-automation: first "self-buff" item action.

Potion of Heroism (RAW DMG p.187, rare consumable) is the first item
whose action buffs the DRINKER rather than targeting others. Drinking
it (``/use_item_action`` with ``action_key: "drink"``) grants 10
temporary hit points + the Bless effect (no concentration) for 1 hour,
then consumes the potion. Two things make it a new archetype vs. the
Phase 3-8 items:

  - ``consumable: True`` in the catalog: the dispatch skips the
    equipped-slot gate and decrements ``qty`` on use.
  - ``self_buff`` config: a flat (non-per-turn) temp-HP grant + a
    Bless buff installed on the drinker's own combatant, best-effort
    (the buff only lands in an active battle; the temp HP and the
    consumption apply either way).

Demo fixture: Garrik Ironside (Fighter Champion) carries a Potion of
Heroism. The fixture snapshots + restores his inventory so the
consume in the happy-path test doesn't permanently deplete the seed
across re-runs against the same container.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _sheet(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    return (r.json() or {}).get("sheet") or {}


def _potion_index(inventory):
    for i, it in enumerate(inventory):
        if isinstance(it, dict) and (it.get("_slug") or "") == "potion-of-heroism":
            return i
    return -1


@pytest_asyncio.fixture
async def garrik_potion(gm_client, roster):
    """Resolve Garrik's Potion-of-Heroism inventory index; snapshot the
    full inventory and restore it in teardown (the happy-path test
    consumes the potion)."""
    garrik = roster["Garrik Ironside"]
    sheet = await _sheet(gm_client, garrik["id"])
    inventory = list(sheet.get("inventory") or [])
    idx = _potion_index(inventory)
    assert idx >= 0, "Garrik must carry a seeded Potion of Heroism"
    try:
        yield {"char": garrik, "index": idx}
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/sheet-fields",
            json={"inventory": inventory},
        )


async def test_drink_potion_of_heroism_grants_temp_hp_and_consumes(
    gm_client, gm_ws, garrik_potion,
):
    """Happy path: drinking grants 10 temp HP, consumes the potion,
    and broadcasts the HP update + feature-used log line. Out of
    combat the Bless buff install is best-effort (no battle), but the
    temp HP + consumption still land."""
    garrik = garrik_potion["char"]
    idx = garrik_potion["index"]
    gm_ws.mark()

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/use_item_action",
        json={"inventory_index": idx, "action_key": "drink"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["item_name"] == "Potion of Heroism"
    assert body["action_key"] == "drink"
    assert body["temp_hp_granted"] == 10
    assert body["temp_hp"] >= 10  # non-stacking max(existing, 10)
    assert body["consumed"] is True
    assert body["buff_key"] == "bless"
    assert isinstance(body["buff_installed"], bool)

    # WS: the client reads character_hp_update.data.hp to redraw the
    # HP meter; assert the temp HP is reflected.
    hp_msg = await gm_ws.wait_for("character_hp_update")
    assert hp_msg["data"]["character_id"] == garrik["id"]
    assert int(hp_msg["data"]["hp"]["temp"]) >= 10

    # Sheet reflects the temp HP and the consumed potion (qty 1 → row
    # removed, so the slug is gone from inventory).
    sheet = await _sheet(gm_client, garrik["id"])
    assert int((sheet.get("hp") or {}).get("temp") or 0) >= 10
    assert _potion_index(sheet.get("inventory") or []) == -1


async def test_drink_potion_of_heroism_unknown_action_404(
    gm_client, garrik_potion,
):
    """Dispatch guard: an action_key the item doesn't define → 404
    (e.g. 'quaff' instead of 'drink'). This exercises the contract
    surface without consuming the potion."""
    garrik = garrik_potion["char"]
    idx = garrik_potion["index"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/use_item_action",
        json={"inventory_index": idx, "action_key": "quaff"},
    )
    assert resp.status_code == 404, resp.text


async def test_use_item_action_missing_fields_400(gm_client, roster):
    """Contract guard: omitting action_key → 400. No item touched."""
    garrik = roster["Garrik Ironside"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/use_item_action",
        json={"inventory_index": 0},
    )
    assert resp.status_code == 400, resp.text
