"""v2.158.87 — magic-items-automation Phase 4c: Wand of Fireballs
through the same `/use_item_action` endpoint as the Wand of Magic
Missiles (v2.158.84), via the generalized `_use_item_action_charge_wand`
handler. RAW DMG p.212: 1 charge casts Fireball at 3rd level; each
additional charge bumps the slot up by 1.

Key difference from the MM wand: `base_slot_level: 3` in the catalog
so cast_slot_level = base + (charges-1). MM had base=1 (charges ==
slot level); Fireball has base=3 (1 charge → Lv 3, 7 charges → Lv 9).

The Fireballs wand is rare RAW → requires attunement. Thalindra
attunes both Pearl + Cloak + Fireballs wand in her seed (3 attuned
items, exactly at the RAW cap).

Tests:
  - happy: spend 1 charge → cast_slot_level = 3 (Lv 3 Fireball).
  - multi-charge: spend 3 charges → cast_slot_level = 5 (Lv 5).
  - unattuned guard: PATCH wand attuned=False → 409 attunement
    required. Restored in teardown.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


# Thalindra's inventory indices (as of v2.158.87):
#   0  Quarterstaff
#   1  Spellbook
#   2  Component pouch
#   3  Scholar's pack
#   4  Robes
#   5  Ink and quill
#   6  Small knife
#   7  Cloak of Protection (attuned: True)
#   8  Pearl of Power      (attuned: True)
#   9  Wand of Magic Missiles (attuned: False — uncommon RAW)
#  10  Wand of Fireballs   (attuned: True — rare RAW)
THALINDRA_FIREBALL_WAND_IDX = 10


async def _long_rest(gm_client, char_id: int) -> None:
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )
    assert resp.status_code == 200, resp.text


@pytest_asyncio.fixture
async def thalindra_fireball_ready(gm_client, roster):
    """Long-rest to refresh; teardown long-rests."""
    thalindra = roster["Thalindra Moonwhisper"]
    await _long_rest(gm_client, thalindra["id"])
    yield thalindra
    await _long_rest(gm_client, thalindra["id"])


async def test_fireball_wand_single_charge_casts_lv3(
    gm_client, thalindra_fireball_ready,
):
    """v2.158.87 happy path. 1 charge → Lv 3 cast (RAW DMG p.212:
    base slot level 3 for Fireball wand)."""
    thalindra = thalindra_fireball_ready
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/use_item_action",
        json={
            "inventory_index": THALINDRA_FIREBALL_WAND_IDX,
            "action_key": "cast-fireball",
            "charges": 1,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["item_name"] == "Wand of Fireballs"
    assert body["spell_slug"] == "fireball"
    assert body["charges_spent"] == 1
    # Fireball base = 3 → 1 charge casts at Lv 3.
    assert body["cast_slot_level"] == 3


async def test_fireball_wand_multi_charge_casts_higher(
    gm_client, thalindra_fireball_ready,
):
    """v2.158.87 base+(charges-1): 3 charges → Lv 5 cast."""
    thalindra = thalindra_fireball_ready
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/use_item_action",
        json={
            "inventory_index": THALINDRA_FIREBALL_WAND_IDX,
            "action_key": "cast-fireball",
            "charges": 3,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["charges_spent"] == 3
    # base=3, charges=3 → 3 + (3-1) = 5.
    assert body["cast_slot_level"] == 5


async def test_fireball_wand_requires_attunement_409(
    gm_client, thalindra_fireball_ready,
):
    """v2.158.87 RAW gate: Wand of Fireballs (rare) requires
    attunement. Detune via /attune → 409 attunement required."""
    thalindra = thalindra_fireball_ready
    # Detune the Fireball wand.
    detune = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/attune",
        json={
            "inventory_index": THALINDRA_FIREBALL_WAND_IDX,
            "attuned": False,
        },
    )
    assert detune.status_code == 200, detune.text
    try:
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/use_item_action",
            json={
                "inventory_index": THALINDRA_FIREBALL_WAND_IDX,
                "action_key": "cast-fireball",
                "charges": 1,
            },
        )
        assert resp.status_code == 409, resp.text
    finally:
        # Restore attunement so downstream tests see the seed state.
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/attune",
            json={
                "inventory_index": THALINDRA_FIREBALL_WAND_IDX,
                "attuned": True,
            },
        )
