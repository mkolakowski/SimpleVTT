"""v2.185.0 — second "self-buff" consumable through the generic
`_use_item_action_self_buff_potion` handler. Potion of Speed (RAW DMG
p.187, very rare): `/use_item_action` with `action_key: "drink"` grants
the DRINKER the Haste effect (no concentration) for 1 minute, then
consumes the potion. Unlike Potion of Heroism (v2.184.0) it grants NO
temp HP — so the handler skips the temp-HP grant + the HP broadcast and
only emits the feature-used log line.

Demo: Garrik Ironside carries a Potion of Speed alongside his Potion of
Heroism. The fixture snapshots + restores his inventory so the consume
doesn't deplete the seed across re-runs against the same container.
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
async def garrik_speed(gm_client, roster):
    """Resolve Garrik's Potion-of-Speed inventory index; snapshot the
    full inventory and restore it in teardown (the happy-path test
    consumes the potion)."""
    garrik = roster["Garrik Ironside"]
    sheet = await _sheet(gm_client, garrik["id"])
    inventory = list(sheet.get("inventory") or [])
    idx = _slug_index(inventory, "potion-of-speed")
    assert idx >= 0, "Garrik must carry a seeded Potion of Speed"
    try:
        yield {"char": garrik, "index": idx}
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/sheet-fields",
            json={"inventory": inventory},
        )


async def test_drink_potion_of_speed_grants_haste_and_consumes(
    gm_client, gm_ws, garrik_speed,
):
    """Happy path: drinking grants the Haste buff (best-effort install)
    and consumes the potion, with NO temp HP. Broadcasts the
    feature-used log line; the drinker's temp HP is untouched."""
    garrik = garrik_speed["char"]
    idx = garrik_speed["index"]
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
    assert body["item_name"] == "Potion of Speed"
    assert body["action_key"] == "drink"
    assert body["buff_key"] == "haste"
    assert body["temp_hp_granted"] == 0  # Speed grants no temp HP
    assert body["consumed"] is True
    assert isinstance(body["buff_installed"], bool)

    # WS: feature-used log line names the drinker + the Haste effect.
    msg = await gm_ws.wait_for("feature_used")
    assert msg["data"]["character_id"] == garrik["id"]
    assert "Haste" in (msg["data"].get("summary") or "")

    # Sheet: temp HP unchanged; the potion row is gone (qty 1 → removed).
    sheet = await _sheet(gm_client, garrik["id"])
    assert int((sheet.get("hp") or {}).get("temp") or 0) == pre_temp
    assert _slug_index(sheet.get("inventory") or [], "potion-of-speed") == -1


async def test_drink_potion_of_speed_unknown_action_404(
    gm_client, garrik_speed,
):
    """Dispatch guard: an action_key the item doesn't define → 404
    (e.g. 'quaff' instead of 'drink'); potion untouched."""
    garrik = garrik_speed["char"]
    idx = garrik_speed["index"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/use_item_action",
        json={"inventory_index": idx, "action_key": "quaff"},
    )
    assert resp.status_code == 404, resp.text
