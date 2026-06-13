"""v2.205.0 — magic-items-automation content tail: Wand of Lightning
Bolts through the same `/use_item_action` endpoint as the Wand of
Fireballs (v2.158.87), via the generalized `_use_item_action_charge_wand`
handler. RAW DMG p.213: 1 charge casts Lightning Bolt at 3rd level;
each additional charge bumps the slot up by 1.

Identical template to the Fireballs wand (`base_slot_level: 3`) — the
only differences are the spell (`lightning-bolt`, a 100-ft line vs the
Fireball sphere) and the demo home: it's seeded on Garrik (Fighter),
not Thalindra, because she's already at the RAW 3-item attunement cap
(Cloak + Pearl + Fireballs wand). Garrik attunes nothing else, so this
is his first attuned item; RAW wands carry no class restriction.

The wand index is looked up by `_slug` rather than hardcoded because
Garrik's inventory grew a long potion tail across v2.184–v2.204.

Tests:
  - happy: spend 1 charge → cast_slot_level = 3 (Lv 3 Lightning Bolt).
  - multi-charge: spend 3 charges → cast_slot_level = 5 (Lv 5).
  - unattuned guard: detune via /attune → 409 attunement required.
    Restored in teardown.
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


async def _long_rest(gm_client, char_id: int) -> None:
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )
    assert resp.status_code == 200, resp.text


@pytest_asyncio.fixture
async def garrik_wand_ready(gm_client, roster):
    """Long-rest to refresh charges; teardown long-rests."""
    garrik = roster["Garrik Ironside"]
    await _long_rest(gm_client, garrik["id"])
    sheet = await _sheet(gm_client, garrik["id"])
    idx = _slug_index(
        sheet.get("inventory") or [], "wand-of-lightning-bolts",
    )
    assert idx >= 0, "Garrik must carry a seeded Wand of Lightning Bolts"
    yield {"char": garrik, "idx": idx}
    await _long_rest(gm_client, garrik["id"])


async def test_lightning_wand_single_charge_casts_lv3(
    gm_client, garrik_wand_ready,
):
    """Happy path. 1 charge → Lv 3 cast (RAW DMG p.213: base slot
    level 3 for the Lightning Bolt wand)."""
    garrik = garrik_wand_ready["char"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/use_item_action",
        json={
            "inventory_index": garrik_wand_ready["idx"],
            "action_key": "cast-lightning-bolt",
            "charges": 1,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["item_name"] == "Wand of Lightning Bolts"
    assert body["spell_slug"] == "lightning-bolt"
    assert body["charges_spent"] == 1
    assert body["cast_slot_level"] == 3


async def test_lightning_wand_multi_charge_casts_higher(
    gm_client, garrik_wand_ready,
):
    """base+(charges-1): 3 charges → Lv 5 cast."""
    garrik = garrik_wand_ready["char"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/use_item_action",
        json={
            "inventory_index": garrik_wand_ready["idx"],
            "action_key": "cast-lightning-bolt",
            "charges": 3,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["charges_spent"] == 3
    assert body["cast_slot_level"] == 5


async def test_lightning_wand_requires_attunement_409(
    gm_client, garrik_wand_ready,
):
    """RAW gate: Wand of Lightning Bolts (rare) requires attunement.
    Detune via /attune → 409 attunement required."""
    garrik = garrik_wand_ready["char"]
    idx = garrik_wand_ready["idx"]
    detune = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/attune",
        json={"inventory_index": idx, "attuned": False},
    )
    assert detune.status_code == 200, detune.text
    try:
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/use_item_action",
            json={
                "inventory_index": idx,
                "action_key": "cast-lightning-bolt",
                "charges": 1,
            },
        )
        assert resp.status_code == 409, resp.text
    finally:
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/attune",
            json={"inventory_index": idx, "attuned": True},
        )
