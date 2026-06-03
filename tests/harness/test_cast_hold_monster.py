"""v2.99.108 — /cast_hold_monster endpoint tests.

L5 concentration spell. Bard / Sorcerer / Warlock / Wizard.
Mirrors /cast_hold_person but targets any creature except Undead,
not just Humanoids. Same Paralyzed factory → same speed→0 effect.

RAW upcast: 1 target at L5, +1 per upcast level. Cap enforced via
409 too_many_targets.

The demo's casters don't have L5 slots by default (Thalindra at
Lv 7 doesn't reach L5 slots until Wizard Lv 9). The fixture
PATCHes Thalindra's spell_slots to add L5 = 1 + her spells list
to include Hold Monster. Restores both in teardown.

Tests:
  - happy path (Thalindra casts at L5 on Krieger → speed→0)
  - upcast L6 with 2 targets → max_targets=2
  - L5 with 2 targets → 409 too_many_targets
  - L4 slot → 400 (Hold Monster is L5)
  - wrong class (cleric) → 400
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _mkc(cid, char_id=None, name="X", speed_walk=30):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": 50, "hp_max": 50,
        "speed_walk": speed_walk,
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False,
                    "movement": 0, "dash_bonus_ft": 0},
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


@pytest_asyncio.fixture
async def thalindra_with_hold_monster(gm_client, roster):
    """Demo Thalindra is Lv 7 Wizard so her stock spell_slots only
    reach L4. v2.99.108 added Hold Monster to her spell list
    (descriptive at Lv 7); this fixture PATCHes her spell_slots to
    include 1 L5 slot so the harness can exercise the endpoint.
    Teardown restores the stock spell_slots map (L1-L4 only).
    """
    thalindra = roster["Thalindra Moonwhisper"]
    # Stock Thalindra's spell_slots from app/demo_seed.py:556-562.
    stock_wizard_slots = {
        "1": {"total": 4, "used": 0},
        "2": {"total": 3, "used": 0},
        "3": {"total": 3, "used": 0},
        "4": {"total": 1, "used": 0},
    }
    test_wizard_slots = dict(stock_wizard_slots, **{
        "5": {"total": 1, "used": 0},
    })
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-fields",
        json={"spell_slots": {"wizard": test_wizard_slots}},
    )
    yield thalindra
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-fields",
        json={"spell_slots": {"wizard": stock_wizard_slots}},
    )


async def test_cast_hold_monster_installs_paralyzed_at_l5(
    gm_client, thalindra_with_hold_monster, roster,
):
    """Thalindra casts Hold Monster at L5 on Krieger (40 ft base) →
    speed_reduction = 40 → effective speed 0.
    """
    thalindra = thalindra_with_hold_monster
    krieger = roster["Krieger Stonefist"]
    th_tok = f"tok_hm_th_{thalindra['id']}"
    kr_tok = f"tok_hm_kr_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(th_tok, thalindra["id"], name=thalindra["name"], speed_walk=30),
        _mkc(kr_tok, krieger["id"], name=krieger["name"], speed_walk=40),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hold_monster",
        json={
            "character_id": thalindra["id"],
            "class_slug": "wizard",
            "slot_level": 5,
            "target_combatant_ids": [kr_tok],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["max_targets"] == 1  # L5 → 1 target
    affected = data["affected"]
    assert len(affected) == 1
    assert affected[0]["speed_reduction_ft"] == 40
    assert affected[0]["installed"] is True


async def test_cast_hold_monster_upcast_l6_max_2(
    gm_client, thalindra_with_hold_monster,
):
    """L6 upcast → 2 targets max. Send 2 fake IDs to verify the
    cap arithmetic; both fail to resolve (unaffected: not_found)
    but the cap gate doesn't fire.
    """
    thalindra = thalindra_with_hold_monster
    # Need L6 slot, not just L5.
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-fields",
        json={"spell_slots": {"wizard": {
            "1": {"total": 4, "used": 0},
            "2": {"total": 3, "used": 0},
            "3": {"total": 3, "used": 0},
            "4": {"total": 1, "used": 0},
            "5": {"total": 1, "used": 0},
            "6": {"total": 1, "used": 0},
        }}},
    )
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hold_monster",
        json={
            "character_id": thalindra["id"],
            "class_slug": "wizard",
            "slot_level": 6,
            "target_combatant_ids": ["fakeA", "fakeB"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["max_targets"] == 2
    assert len(data["unaffected"]) == 2  # both fakes


async def test_cast_hold_monster_l5_with_2_targets_rejected(
    gm_client, thalindra_with_hold_monster,
):
    """L5 caps at 1. 2 targets → 409 too_many_targets."""
    thalindra = thalindra_with_hold_monster
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hold_monster",
        json={
            "character_id": thalindra["id"],
            "class_slug": "wizard",
            "slot_level": 5,
            "target_combatant_ids": ["a", "b"],
            "override": True,
        },
    )
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert data["error"] == "too_many_targets"
    assert data["max"] == 1


async def test_cast_hold_monster_l4_slot_rejected(
    gm_client, thalindra_with_hold_monster,
):
    """slot_level=4 → 400 (Hold Monster is L5)."""
    thalindra = thalindra_with_hold_monster
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hold_monster",
        json={
            "character_id": thalindra["id"],
            "class_slug": "wizard",
            "slot_level": 4,
            "target_combatant_ids": ["a"],
            "override": True,
        },
    )
    assert resp.status_code == 400, resp.text


async def test_cast_hold_monster_rejects_cleric_class(gm_client, roster):
    """Cleric isn't in Hold Monster's class list (no Cleric on the
    Hold Monster spell list per RAW). class_slug="cleric" → 400.
    """
    tavik = roster["Brother Tavik Stonebrow"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hold_monster",
        json={
            "character_id": tavik["id"],
            "class_slug": "cleric",
            "slot_level": 5,
            "target_combatant_ids": ["a"],
            "override": True,
        },
    )
    assert resp.status_code == 400, resp.text
