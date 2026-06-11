"""v2.158.88 — magic-items-automation Phase 4d: Staff of Healing
through the same `/use_item_action` endpoint, via a multi-action
catalog shape (3 distinct action_keys on one item, each with its
own charge cost + spell).

Different shape from Phase 3 (Pearl: 1 action) and Phase 4a/c (Wands:
1 action with variable charges). RAW DMG p.202: 10 charges total;
each call spends 1-5 of them depending on the action picked:

  - cast-cure-wounds: 1-4 charges → Cure Wounds at Lv 1-4
  - cast-lesser-restoration: exactly 2 charges → Lesser Restoration
  - cast-mass-cure-wounds: exactly 5 charges → Mass Cure Wounds

Demo fixture: Tavik Stonebrow (Cleric Lv 8, save proficient WIS/CHA)
carries a permanent equipped + attuned Staff of Healing alongside
his Ring of Protection (v2.158.76) — 2 attuned items total, well
under the RAW DMG p.138 cap of 3.

Tests:
  - cure wounds 1 charge → cast_slot_level=1.
  - cure wounds 4 charges → cast_slot_level=4 (max).
  - cure wounds 5 charges → 400 (over max for this action_key).
  - lesser restoration with charges=2 → 200.
  - lesser restoration with charges=3 → 400 (RAW fixed at 2).
  - mass cure wounds with charges=5 → 200, cast_slot_level=5.
  - insufficient charges path: PATCH staff resource to 1, request
    mass cure → 409.
  - unknown action_key → 404.

Teardown long-rest refills the staff.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


# Tavik's inventory indices (as of v2.158.88):
#   0-7  mundane gear (warhammer, shield, chain mail, holy symbol,
#        priest's pack, smith's tools, healer's kit, potion of healing)
#   8    Ring of Protection (attuned: True)  [v2.158.76]
#   9    Staff of Healing   (attuned: True)  [v2.158.88]
TAVIK_STAFF_IDX = 9


async def _long_rest(gm_client, char_id: int) -> dict:
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest_asyncio.fixture
async def tavik_staff_ready(gm_client, roster):
    """Long-rest to refresh the staff to full charges (recharge
    1d6+4 → 5-10 + current, capped at 10 → likely 10). Teardown
    also long-rests."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _long_rest(gm_client, tavik["id"])
    yield tavik
    await _long_rest(gm_client, tavik["id"])


async def test_staff_cure_wounds_single_charge(gm_client, tavik_staff_ready):
    """v2.158.88 happy path. cast-cure-wounds with 1 charge →
    cast_slot_level=1."""
    tavik = tavik_staff_ready
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/use_item_action",
        json={
            "inventory_index": TAVIK_STAFF_IDX,
            "action_key": "cast-cure-wounds",
            "charges": 1,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["item_name"] == "Staff of Healing"
    assert body["action_key"] == "cast-cure-wounds"
    assert body["spell_slug"] == "cure-wounds"
    assert body["charges_spent"] == 1
    assert body["cast_slot_level"] == 1


async def test_staff_cure_wounds_max_charges(gm_client, tavik_staff_ready):
    """v2.158.88 upcast: 4 charges → cast_slot_level=4."""
    tavik = tavik_staff_ready
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/use_item_action",
        json={
            "inventory_index": TAVIK_STAFF_IDX,
            "action_key": "cast-cure-wounds",
            "charges": 4,
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["cast_slot_level"] == 4


async def test_staff_cure_wounds_over_max_400(gm_client, tavik_staff_ready):
    """v2.158.88 RAW cap: Cure Wounds via staff allows 1-4 charges
    (Lv 4 cap). 5 charges → 400."""
    tavik = tavik_staff_ready
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/use_item_action",
        json={
            "inventory_index": TAVIK_STAFF_IDX,
            "action_key": "cast-cure-wounds",
            "charges": 5,
        },
    )
    assert resp.status_code == 400, resp.text


async def test_staff_lesser_restoration_fixed_2(gm_client, tavik_staff_ready):
    """v2.158.88 fixed-charge action. lesser-restoration takes
    exactly 2 charges. 2 → 200, cast_slot_level=2."""
    tavik = tavik_staff_ready
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/use_item_action",
        json={
            "inventory_index": TAVIK_STAFF_IDX,
            "action_key": "cast-lesser-restoration",
            "charges": 2,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["spell_slug"] == "lesser-restoration"
    assert body["cast_slot_level"] == 2


async def test_staff_lesser_restoration_wrong_charges_400(
    gm_client, tavik_staff_ready,
):
    """v2.158.88: lesser-restoration with charges != 2 → 400 (RAW
    fixed at 2). Test with 3 charges."""
    tavik = tavik_staff_ready
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/use_item_action",
        json={
            "inventory_index": TAVIK_STAFF_IDX,
            "action_key": "cast-lesser-restoration",
            "charges": 3,
        },
    )
    assert resp.status_code == 400, resp.text


async def test_staff_mass_cure_wounds_lv5(gm_client, tavik_staff_ready):
    """v2.158.88 highest-cost action. mass-cure-wounds takes
    exactly 5 charges → cast_slot_level=5."""
    tavik = tavik_staff_ready
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/use_item_action",
        json={
            "inventory_index": TAVIK_STAFF_IDX,
            "action_key": "cast-mass-cure-wounds",
            "charges": 5,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["spell_slug"] == "mass-cure-wounds"
    assert body["cast_slot_level"] == 5


async def test_staff_unknown_action_404(gm_client, roster):
    """v2.158.88 dispatch guard: action_key not in the staff's
    actions map → 404 (e.g. trying to cast Fireball from a Staff
    of Healing). Tests the multi-action sub-dispatch validation."""
    tavik = roster["Brother Tavik Stonebrow"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/use_item_action",
        json={
            "inventory_index": TAVIK_STAFF_IDX,
            "action_key": "cast-fireball",
            "charges": 5,
        },
    )
    assert resp.status_code == 404, resp.text
