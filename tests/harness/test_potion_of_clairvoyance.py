"""v2.203.0 — Potion of Clairvoyance (RAW DMG p.187, rare): drink → the
clairvoyance spell (a scrying sensor for 10 minutes), no concentration.

The eleventh self-buff potion. Like Water Breathing it's a purely
descriptive buff — the engine tracks no scrying rule, so the
`clairvoyance-potion` template has no mechanical effect; it just surfaces
on the init strip with a duration. The contract worth proving is the
install itself: in an active battle the drink reports `buff_installed: True`
and the `clairvoyance-potion` key lands on Garrik's combatant.

Mirrors `test_potion_of_water_breathing.py` — `_install_buff` no-ops
outside combat, so the test puts Garrik in an active solo battle first.
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
    garrik = roster["Garrik Ironside"]
    sheet = await _sheet(gm_client, garrik["id"])
    inventory = list(sheet.get("inventory") or [])
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [{
                "id": f"tok_clair_garrik_{garrik['id']}",
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


async def test_clairvoyance_installs_buff_in_battle(
    gm_client, garrik_in_battle,
):
    """In an active battle, drinking Clairvoyance reports buff_installed
    True + consumed True, and the `clairvoyance-potion` buff lands on
    Garrik's combatant."""
    garrik = garrik_in_battle["char"]
    idx = _slug_index(
        garrik_in_battle["inventory"], "potion-of-clairvoyance",
    )
    assert idx >= 0, "Garrik must carry a seeded Potion of Clairvoyance"

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/use_item_action",
        json={"inventory_index": idx, "action_key": "drink"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["buff_key"] == "clairvoyance-potion", body
    assert body["buff_installed"] is True, body
    assert body["consumed"] is True, body

    assert "clairvoyance-potion" in await _buff_keys(gm_client, garrik["id"])


async def test_clairvoyance_bad_action_key_404(
    gm_client, garrik_in_battle,
):
    """A non-existent action_key on the potion → 404."""
    garrik = garrik_in_battle["char"]
    idx = _slug_index(
        garrik_in_battle["inventory"], "potion-of-clairvoyance",
    )
    assert idx >= 0

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/use_item_action",
        json={"inventory_index": idx, "action_key": "scry"},
    )
    assert resp.status_code == 404, resp.text
