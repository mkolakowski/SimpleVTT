"""v2.99.107 — /cast_hold_person endpoint tests.

Lv 2 concentration spell. Available to Cleric / Bard / Sorcerer /
Warlock / Wizard. v1 ships the speed→0 (Paralyzed) effect via
the new `_make_paralyzed_buff` factory; other Paralyzed mechanics
(auto-fail STR/DEX saves, attacks have advantage, melee auto-crits)
surface as raw_effects for GM narration.

RAW upcasting: 1 target at L2, +1 per upcast level above. v1
enforces the cap via 409 too_many_targets.

Tests:
  - happy path (Tavik casts on Krieger at L2 → 1 target, speed→0)
  - upcast L4 with 3 targets → all 3 affected
  - L2 with 2 targets → 409 too_many_targets
  - L1 slot → 400 (Hold Person is L2)
  - wrong class → 409 (Krieger Barbarian doesn't get Hold Person)
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
async def tavik_and_krieger(gm_client, roster):
    tavik = roster["Brother Tavik Stonebrow"]
    krieger = roster["Krieger Stonefist"]
    tv_tok = f"tok_hp_tv_{tavik['id']}"
    kr_tok = f"tok_hp_kr_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(tv_tok, tavik["id"], name=tavik["name"], speed_walk=30),
        _mkc(kr_tok, krieger["id"], name=krieger["name"], speed_walk=40),
    ])
    yield tavik, krieger, kr_tok


async def test_cast_hold_person_installs_paralyzed_buff(
    gm_client, tavik_and_krieger,
):
    """Tavik (Cleric Lv 6) casts Hold Person at L2 on Krieger.
    Buff installs with speed_reduction_ft = 40 (Krieger's full
    base speed → effective speed 0).
    """
    tavik, krieger, kr_tok = tavik_and_krieger
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hold_person",
        json={
            "character_id": tavik["id"],
            "class_slug": "cleric",
            "slot_level": 2,
            "target_combatant_ids": [kr_tok],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["duration_rounds"] == 10
    assert data["concentration"] is True
    assert data["max_targets"] == 1  # L2 → 1 target
    affected = data.get("affected") or []
    assert len(affected) == 1, affected
    entry = affected[0]
    assert entry["combatant_id"] == kr_tok
    assert entry["base_speed_walk"] == 40
    assert entry["speed_reduction_ft"] == 40, entry
    assert entry["installed"] is True


async def test_cast_hold_person_upcast_l4_allows_3_targets(
    gm_client, roster,
):
    """L4 upcast → 3 targets. Tavik affects Krieger + 2 fakes
    (the fakes won't resolve in hub but the cap check happens
    BEFORE the resolution loop, so they pass the gate; the
    affected list will only include those that resolve).
    """
    tavik = roster["Brother Tavik Stonebrow"]
    krieger = roster["Krieger Stonefist"]
    tv_tok = f"tok_hp_l4_tv_{tavik['id']}"
    kr_tok = f"tok_hp_l4_kr_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(tv_tok, tavik["id"], name=tavik["name"], speed_walk=30),
        _mkc(kr_tok, krieger["id"], name=krieger["name"], speed_walk=40),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hold_person",
        json={
            "character_id": tavik["id"],
            "class_slug": "cleric",
            "slot_level": 4,
            "target_combatant_ids": [kr_tok, "fake1", "fake2"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["max_targets"] == 3  # L4 → 3 targets
    affected = data.get("affected") or []
    unaffected = data.get("unaffected") or []
    assert len(affected) == 1  # only Krieger resolved
    assert len(unaffected) == 2  # fakes not_found
    assert all(u["reason"] == "not_found" for u in unaffected)


async def test_cast_hold_person_l2_with_2_targets_rejected(gm_client, roster):
    """L2 caps at 1 target. 2 targets → 409 too_many_targets."""
    tavik = roster["Brother Tavik Stonebrow"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hold_person",
        json={
            "character_id": tavik["id"],
            "class_slug": "cleric",
            "slot_level": 2,
            "target_combatant_ids": ["a", "b"],
            "override": True,
        },
    )
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert data["error"] == "too_many_targets"
    assert data["max"] == 1
    assert data["got"] == 2


async def test_cast_hold_person_l1_slot_rejected(gm_client, roster):
    """slot_level=1 → 400 (Hold Person is L2)."""
    tavik = roster["Brother Tavik Stonebrow"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hold_person",
        json={
            "character_id": tavik["id"],
            "class_slug": "cleric",
            "slot_level": 1,
            "target_combatant_ids": ["a"],
            "override": True,
        },
    )
    assert resp.status_code == 400, resp.text


async def test_cast_hold_person_rejects_invalid_class(gm_client, roster):
    """Barbarian isn't in the Hold Person class list → 400.
    (Hold Person is on the Cleric/Bard/Sorcerer/Warlock/Wizard
    spell lists.)
    """
    tavik = roster["Brother Tavik Stonebrow"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hold_person",
        json={
            "character_id": tavik["id"],
            "class_slug": "barbarian",
            "slot_level": 2,
            "target_combatant_ids": ["a"],
            "override": True,
        },
    )
    assert resp.status_code == 400, resp.text
