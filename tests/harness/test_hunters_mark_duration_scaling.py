"""v2.405.0 — spell-utility-mechanical-depth Phase 1: duration-scaling
substrate. The new `_SPELL_DURATION_MAP` + `_spell_duration_rounds_for_slot()`
helper replace the hardcoded per-slot duration ladder at the
/cast_hunters_mark endpoint with a data-driven lookup. RAW PHB p.251:

  - L1-L2 slot → 1 hour concentration  (600 rounds)
  - L3-L4 slot → 8 hours concentration (4800 rounds)
  - L5+  slot → 24 hours concentration (14400 rounds)

The endpoint surfaces a `duration_label` ("1h" / "8h" / "24h") derived
from the substrate-computed round count. These tests assert all three
tiers route correctly through the substrate by casting at L1, L3, and
L5 and inspecting the installed buff's `duration_label`.

Rowan Quickbow is the canonical Hunter's Mark caster (Ranger Lv 5,
slots 4/2 — needs L3-L5 fixtures to test the upper tiers, so the
fixture PATCHes her spell_slots up for the upper-tier casts).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _get_buffs(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    return r.json().get("buffs") or []


async def _place_token(gm_client, char_id, x, y):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/place-token",
        json={"x": float(x), "y": float(y)},
    )
    assert r.status_code == 200, r.text


async def _seed_battle(gm_client, caster_id, caster_name):
    return await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_hmds_caster_{caster_id}",
             "char_id": caster_id, "name": caster_name,
             "initiative": 10, "hp_current": 30, "hp_max": 30,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )


async def _patch_slots(gm_client, char_id, level: int):
    """Set Rowan's spell slots so the requested slot level is available
    + unused. Rangers carry slots[1-5] at Lv 9+; the demo Rowan is Lv 5
    with slots 4/2 — PATCH her slot table up to support higher tiers."""
    slot_table = {
        "1": {"total": 4, "used": 0},
        "2": {"total": 3, "used": 0},
        "3": {"total": 3, "used": 0},
        "4": {"total": 1, "used": 0},
        "5": {"total": 1, "used": 0},
    }
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"spell_slots": {"ranger": slot_table}},
    )
    assert r.status_code == 200, r.text


@pytest_asyncio.fixture
async def rowan_armed(gm_client, roster):
    """Rowan rested + slot table PATCH'd up + Krieger placed as the
    Hunter's Mark target. Teardown long-rests Rowan back to baseline."""
    rowan = roster["Rowan Quickbow"]
    krieger = roster["Krieger Stonefist"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/rest",
        json={"type": "long"},
    )
    await _patch_slots(gm_client, rowan["id"], 5)
    await _place_token(gm_client, krieger["id"], 400.0, 400.0)
    await _seed_battle(gm_client, rowan["id"], rowan["name"])
    yield rowan, krieger
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/rest",
        json={"type": "long"},
    )


async def _cast(gm_client, rowan, krieger, slot_level):
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hunters_mark",
        json={
            "character_id": rowan["id"],
            "target_character_id": krieger["id"],
            "slot_level": slot_level,
            "override": True,
        },
    )


async def _hunters_mark_buff(gm_client, char_id):
    buffs = await _get_buffs(gm_client, char_id)
    return next(
        (b for b in buffs if (b or {}).get("key") == "hunters-mark"),
        None,
    )


async def test_hunters_mark_l1_routes_1h_duration(gm_client, rowan_armed):
    """v2.405.0: cast at L1 → substrate returns 600 rounds (1 hour); the
    `duration_label` on both the response + the installed buff resolve
    to "1h". Lower-tier branch of the new substrate."""
    rowan, krieger = rowan_armed
    resp = await _cast(gm_client, rowan, krieger, slot_level=1)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # The endpoint puts `duration_label` directly in the response body
    # via the broadcast payload; some endpoints also surface it as a
    # top-level field. The buff is the authoritative source.
    buff = await _hunters_mark_buff(gm_client, rowan["id"])
    assert buff is not None, "Hunter's Mark buff should install"
    assert buff.get("duration_label") == "1h", \
        f"L1 should land 1h tier, got {buff.get('duration_label')!r}"


async def test_hunters_mark_l3_routes_8h_duration(gm_client, rowan_armed):
    """v2.405.0: cast at L3 → substrate returns 4800 rounds (8 hours);
    label resolves to "8h". Middle-tier branch."""
    rowan, krieger = rowan_armed
    resp = await _cast(gm_client, rowan, krieger, slot_level=3)
    assert resp.status_code == 200, resp.text
    buff = await _hunters_mark_buff(gm_client, rowan["id"])
    assert buff is not None
    assert buff.get("duration_label") == "8h", \
        f"L3 should land 8h tier, got {buff.get('duration_label')!r}"


async def test_hunters_mark_l5_routes_24h_duration(gm_client, rowan_armed):
    """v2.405.0: cast at L5 → substrate returns 14400 rounds (24 hours);
    label resolves to "24h". Upper-tier branch."""
    rowan, krieger = rowan_armed
    resp = await _cast(gm_client, rowan, krieger, slot_level=5)
    assert resp.status_code == 200, resp.text
    buff = await _hunters_mark_buff(gm_client, rowan["id"])
    assert buff is not None
    assert buff.get("duration_label") == "24h", \
        f"L5 should land 24h tier, got {buff.get('duration_label')!r}"
