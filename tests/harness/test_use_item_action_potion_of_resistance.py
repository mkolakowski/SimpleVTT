"""v2.186.0 — third "self-buff" consumable through the generic
`_use_item_action_self_buff_potion` handler. Potion of Resistance (RAW
DMG p.188, uncommon): `/use_item_action` with `action_key: "drink"`
grants the DRINKER resistance to one damage type for 1 hour, then
consumes the potion. v1 ships the fire instance.

Unlike Heroism (Bless markers) and Speed (Haste +AC/+speed), this is
the first self-buff whose effect is mechanically ENFORCED rather than a
display marker: the `resistance-fire` buff carries
`effects.resistance_to: ["fire"]`, which the live damage pipeline
(`_resistance_halve`) reads to halve incoming fire damage. The in-battle
test asserts the installed buff actually carries that effect.

Demo: Garrik Ironside carries a Potion of Fire Resistance alongside his
Heroism + Speed potions. The fixtures snapshot + restore his inventory.
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


@pytest_asyncio.fixture
async def garrik_resistance(gm_client, roster):
    """Resolve Garrik's Potion-of-Resistance inventory index; snapshot
    the full inventory and restore it in teardown (the happy-path tests
    consume the potion)."""
    garrik = roster["Garrik Ironside"]
    sheet = await _sheet(gm_client, garrik["id"])
    inventory = list(sheet.get("inventory") or [])
    idx = _slug_index(inventory, "potion-of-resistance")
    assert idx >= 0, "Garrik must carry a seeded Potion of Resistance"
    try:
        yield {"char": garrik, "index": idx}
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/sheet-fields",
            json={"inventory": inventory},
        )


async def test_drink_potion_of_resistance_grants_buff_and_consumes(
    gm_client, gm_ws, garrik_resistance,
):
    """Happy path: drinking grants the fire-resistance buff (best-effort
    install) and consumes the potion, with NO temp HP. Broadcasts the
    feature-used log line naming the resistance; temp HP untouched."""
    garrik = garrik_resistance["char"]
    idx = garrik_resistance["index"]
    pre = await _sheet(gm_client, garrik["id"])
    pre_temp = int((pre.get("hp") or {}).get("temp") or 0)
    gm_ws.mark()

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/use_item_action",
        json={"inventory_index": idx, "action_key": "drink"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["item_name"] == "Potion of Fire Resistance"
    assert body["action_key"] == "drink"
    assert body["buff_key"] == "resistance-fire"
    assert body["temp_hp_granted"] == 0  # Resistance grants no temp HP
    assert body["consumed"] is True
    assert isinstance(body["buff_installed"], bool)

    msg = await gm_ws.wait_for("feature_used")
    assert msg["data"]["character_id"] == garrik["id"]
    assert "fire" in (msg["data"].get("summary") or "").lower()

    sheet = await _sheet(gm_client, garrik["id"])
    assert int((sheet.get("hp") or {}).get("temp") or 0) == pre_temp
    assert _slug_index(sheet.get("inventory") or [], "potion-of-resistance") == -1


async def test_drink_in_battle_installs_enforced_fire_resistance(
    gm_client, garrik_resistance,
):
    """In an active battle the install lands True AND the installed buff
    carries the live `resistance_to: ["fire"]` effect that the damage
    pipeline reads — proving this self-buff is mechanically enforced, not
    a display marker."""
    garrik = garrik_resistance["char"]
    idx = garrik_resistance["index"]
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [{
                "id": f"tok_resist_garrik_{garrik['id']}",
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
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/use_item_action",
            json={"inventory_index": idx, "action_key": "drink"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["buff_installed"] is True

        r = await gm_client.get(
            f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/buffs",
        )
        assert r.status_code == 200, r.text
        buffs = r.json().get("buffs") or []
        fire = next(
            (b for b in buffs if (b or {}).get("key") == "resistance-fire"),
            None,
        )
        assert fire is not None, f"resistance-fire buff missing; got {buffs}"
        resists = (fire.get("effects") or {}).get("resistance_to") or []
        assert "fire" in [str(x).lower() for x in resists]
    finally:
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={"combatants": [], "turn_index": 0, "round": 1,
                  "active": False},
        )


async def test_drink_potion_of_resistance_unknown_action_404(
    gm_client, garrik_resistance,
):
    """Dispatch guard: an action_key the item doesn't define → 404
    (e.g. 'quaff' instead of 'drink'); potion untouched."""
    garrik = garrik_resistance["char"]
    idx = garrik_resistance["index"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/use_item_action",
        json={"inventory_index": idx, "action_key": "quaff"},
    )
    assert resp.status_code == 404, resp.text
