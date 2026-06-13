"""v2.204.0 — Potion of Gaseous Form (RAW DMG p.187, rare): drink → the
gaseous form spell for up to 1 hour, no concentration.

The twelfth self-buff potion. It carries a real, composable engine effect:
`effects.resistance_to` lists every `nonmagical-<type>` entry the F6 matcher
understands, so `_resistance_halve` halves any nonmagical hit while letting
magical-source damage through; plus `effects.fly_speed_ft: 10` for the
hover. The save advantage and the can't-act restriction are GM-narrated.

The contract worth proving is the install plus that the installed buff
carries both markers. Mirrors `test_potion_of_invisibility.py` —
`_install_buff` no-ops outside combat, so the test puts Garrik in an active
solo battle first.
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
                "id": f"tok_gas_garrik_{garrik['id']}",
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


async def test_gaseous_form_installs_buff_with_markers(
    gm_client, garrik_in_battle,
):
    """In an active battle, drinking Gaseous Form reports buff_installed
    True + consumed True; the `gaseous-form-potion` buff lands on Garrik's
    combatant carrying both the nonmagical `resistance_to` list and the
    `fly_speed_ft` hover marker."""
    garrik = garrik_in_battle["char"]
    idx = _slug_index(garrik_in_battle["inventory"], "potion-of-gaseous-form")
    assert idx >= 0, "Garrik must carry a seeded Potion of Gaseous Form"

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/use_item_action",
        json={"inventory_index": idx, "action_key": "drink"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["buff_key"] == "gaseous-form-potion", body
    assert body["buff_installed"] is True, body
    assert body["consumed"] is True, body

    buffs = await _buffs(gm_client, garrik["id"])
    gas = next(
        (b for b in buffs if (b or {}).get("key") == "gaseous-form-potion"),
        None,
    )
    assert gas is not None, buffs
    effects = gas.get("effects") or {}
    resists = [str(r).lower() for r in (effects.get("resistance_to") or [])]
    assert "nonmagical-bludgeoning" in resists, gas
    assert (effects.get("fly_speed_ft") or 0) > 0, gas


async def test_gaseous_form_bad_action_key_404(gm_client, garrik_in_battle):
    """A non-existent action_key on the potion → 404."""
    garrik = garrik_in_battle["char"]
    idx = _slug_index(garrik_in_battle["inventory"], "potion-of-gaseous-form")
    assert idx >= 0

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/use_item_action",
        json={"inventory_index": idx, "action_key": "vaporize"},
    )
    assert resp.status_code == 404, resp.text
