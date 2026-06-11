"""v2.158.84 — magic-items-automation Phase 4a: Wand of Magic Missiles
through the `/use_item_action` endpoint.

Different shape from Pearl of Power (v2.158.82): multi-charge spend
per use. RAW DMG p.213: "expend 1 or more charges to cast Magic
Missile at slot level equal to charges spent (1=Lv 1, 7=Lv 7)".
7 starting charges, recharge 1d6+1 on long rest (dice recharge ships
in Phase 4b — Phase 4a uses the standard reset=long full refill).

Demo fixture: Thalindra Moonwhisper (Wizard Lv 7) carries an equipped
Wand of Magic Missiles in her seed + a `wand-of-magic-missiles`
resource row (current 7, max 7, reset long). The wand doesn't
require attunement (RAW: only rare+ wands need attunement).

Tests:
  - happy: spend 1 charge → resource decrements 7→6, response carries
    cast_slot_level=1.
  - multi-charge: spend 3 charges → 7→4, cast_slot_level=3.
  - insufficient charges: try to spend 8 → 400 (over max_charges).
  - over-spend: deplete to 1, spend 2 → 409 `insufficient_charges`.
  - error paths: unknown action_key → 404, missing fields → 400.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


# Thalindra's inventory indices (as of v2.158.84):
#   0  Quarterstaff
#   1  Spellbook
#   2  Component pouch
#   3  Scholar's pack
#   4  Robes
#   5  Ink and quill
#   6  Small knife
#   7  Cloak of Protection (attuned: True)
#   8  Pearl of Power      (attuned: True)
#   9  Wand of Magic Missiles (attuned: False — RAW uncommon doesn't need it)
THALINDRA_WAND_IDX = 9


async def _long_rest(gm_client, char_id: int) -> None:
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )
    assert resp.status_code == 200, resp.text


@pytest_asyncio.fixture
async def thalindra_full_wand(gm_client, roster):
    """Reset Thalindra to a known state with the wand at full
    charges (7) via long rest. Teardown also long-rests."""
    thalindra = roster["Thalindra Moonwhisper"]
    await _long_rest(gm_client, thalindra["id"])
    yield thalindra
    await _long_rest(gm_client, thalindra["id"])


async def test_use_wand_single_charge(gm_client, thalindra_full_wand):
    """v2.158.84 happy path. Spending 1 charge → Lv 1 Magic Missile;
    resource drops 7→6."""
    thalindra = thalindra_full_wand
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/use_item_action",
        json={
            "inventory_index": THALINDRA_WAND_IDX,
            "action_key": "cast-magic-missile",
            "charges": 1,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["item_name"] == "Wand of Magic Missiles"
    assert body["spell_slug"] == "magic-missile"
    assert body["charges_spent"] == 1
    assert body["cast_slot_level"] == 1
    assert body["resource"]["current"] == 6
    assert body["resource"]["max"] == 7


async def test_use_wand_multi_charge(gm_client, thalindra_full_wand):
    """v2.158.84 multi-charge: spending 3 charges → Lv 3 cast,
    resource 7→4."""
    thalindra = thalindra_full_wand
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/use_item_action",
        json={
            "inventory_index": THALINDRA_WAND_IDX,
            "action_key": "cast-magic-missile",
            "charges": 3,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["charges_spent"] == 3
    assert body["cast_slot_level"] == 3
    assert body["resource"]["current"] == 4


async def test_use_wand_over_max_charges_400(
    gm_client, thalindra_full_wand,
):
    """v2.158.84 RAW cap: requesting 8 charges → 400 (Wand has 7
    charges max RAW, even when fully refilled)."""
    thalindra = thalindra_full_wand
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/use_item_action",
        json={
            "inventory_index": THALINDRA_WAND_IDX,
            "action_key": "cast-magic-missile",
            "charges": 8,
        },
    )
    assert resp.status_code == 400, resp.text


async def test_use_wand_insufficient_charges_409(
    gm_client, thalindra_full_wand,
):
    """v2.158.84 charge cap: deplete the wand to 1 charge by
    spending 6, then try to spend 2 more → 409
    `insufficient_charges`."""
    thalindra = thalindra_full_wand
    # Burn 6 charges so wand has 1 left.
    r1 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/use_item_action",
        json={
            "inventory_index": THALINDRA_WAND_IDX,
            "action_key": "cast-magic-missile",
            "charges": 6,
        },
    )
    assert r1.status_code == 200, r1.text
    assert r1.json()["resource"]["current"] == 1
    # Try to spend 2 more — only 1 left.
    r2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/use_item_action",
        json={
            "inventory_index": THALINDRA_WAND_IDX,
            "action_key": "cast-magic-missile",
            "charges": 2,
        },
    )
    assert r2.status_code == 409, r2.text
    body = r2.json()
    assert body.get("error") == "insufficient_charges"
    assert body.get("current") == 1
    assert body.get("requested") == 2


async def test_use_wand_unknown_action_404(gm_client, roster):
    """v2.158.84 dispatch guard: a non-wand action_key → 404."""
    thalindra = roster["Thalindra Moonwhisper"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/use_item_action",
        json={
            "inventory_index": THALINDRA_WAND_IDX,
            "action_key": "restore-slot",  # Pearl action on a Wand
            "charges": 1,
        },
    )
    assert resp.status_code == 404, resp.text
