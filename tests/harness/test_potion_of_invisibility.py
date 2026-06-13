"""v2.200.0 — Potion of Invisibility (RAW DMG p.188, very rare): drink →
invisible for 1 hour or until you attack or cast a spell, no concentration.

The ninth self-buff potion. Unlike Water Breathing (a purely descriptive
buff) this one carries a real mechanical marker: `effects.invisible: True`,
which the attack-resolution intercepts already honour (an invisible
attacker has advantage). So the contract worth proving is twofold — the
install itself (in an active battle the drink reports `buff_installed: True`
and the `invisibility-potion` key lands on Garrik's combatant) AND that the
installed buff actually carries the `effects.invisible` marker that the
attack code reads.

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
                "id": f"tok_invis_garrik_{garrik['id']}",
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


async def test_invisibility_installs_buff_with_marker(
    gm_client, garrik_in_battle,
):
    """In an active battle, drinking Invisibility reports buff_installed
    True + consumed True, the `invisibility-potion` buff lands on Garrik's
    combatant, AND it carries the `effects.invisible` marker the attack
    code reads."""
    garrik = garrik_in_battle["char"]
    idx = _slug_index(
        garrik_in_battle["inventory"], "potion-of-invisibility",
    )
    assert idx >= 0, "Garrik must carry a seeded Potion of Invisibility"

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/use_item_action",
        json={"inventory_index": idx, "action_key": "drink"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["buff_key"] == "invisibility-potion", body
    assert body["buff_installed"] is True, body
    assert body["consumed"] is True, body

    buffs = await _buffs(gm_client, garrik["id"])
    invis = next(
        (b for b in buffs if (b or {}).get("key") == "invisibility-potion"),
        None,
    )
    assert invis is not None, buffs
    assert (invis.get("effects") or {}).get("invisible") is True, invis


async def test_invisibility_bad_action_key_404(
    gm_client, garrik_in_battle,
):
    """A non-existent action_key on the potion → 404."""
    garrik = garrik_in_battle["char"]
    idx = _slug_index(
        garrik_in_battle["inventory"], "potion-of-invisibility",
    )
    assert idx >= 0

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/use_item_action",
        json={"inventory_index": idx, "action_key": "vanish"},
    )
    assert resp.status_code == 404, resp.text
