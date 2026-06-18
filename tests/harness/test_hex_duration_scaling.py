"""v2.405.1 — spell-utility-mechanical-depth Phase 1: duration-scaling
substrate, second consumer. The v2.405.0 `_SPELL_DURATION_MAP` +
`_spell_duration_rounds_for_slot()` helper replaced Hunter's Mark's
hardcoded per-slot duration ladder; v2.405.1 retrofits /cast_hex the
same way. RAW PHB p.251:

  - L1-L2 slot → 1 hour concentration  (600 rounds)
  - L3-L4 slot → 8 hours concentration (4800 rounds)
  - L5+  slot → 24 hours concentration (14400 rounds)

The endpoint surfaces a `duration_label` ("1h" / "8h" / "24h") on the
installed Hex buff, derived from the substrate-computed round count.
These tests assert all three tiers route correctly through the
substrate by casting at L1, L3, and L5 and inspecting the buff's
`duration_label`.

Magnus Hexbinder is the canonical Hex caster (Warlock Lv 5, Pact Magic
2/2 at L3 only). To exercise the L1 and L5 tiers the fixture PATCHes
his warlock slot table up to L5 (the /cast_hex endpoint picks the
lowest available slot at or above the requested level, so each
requested slot_level lands in its own tier).
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
            {"id": f"tok_hxds_caster_{caster_id}",
             "char_id": caster_id, "name": caster_name,
             "initiative": 10, "hp_current": 30, "hp_max": 30,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )


async def _patch_slots(gm_client, char_id):
    """Give Magnus a full L1-L5 warlock slot table so each requested
    slot level lands in its own duration tier. The demo Magnus is a
    Lv 5 Warlock with Pact Magic 2/2 at L3 only."""
    slot_table = {
        "1": {"total": 2, "used": 0, "reset": "short"},
        "2": {"total": 2, "used": 0, "reset": "short"},
        "3": {"total": 2, "used": 0, "reset": "short"},
        "4": {"total": 2, "used": 0, "reset": "short"},
        "5": {"total": 2, "used": 0, "reset": "short"},
    }
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"spell_slots": {"warlock": slot_table}},
    )
    assert r.status_code == 200, r.text


@pytest_asyncio.fixture
async def magnus_armed(gm_client, roster):
    """Magnus rested + slot table PATCH'd up to L5 + Krieger placed as
    the Hex target. Teardown long-rests Magnus back to baseline."""
    magnus = roster["Magnus Hexbinder"]
    krieger = roster["Krieger Stonefist"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )
    await _patch_slots(gm_client, magnus["id"])
    await _place_token(gm_client, krieger["id"], 400.0, 400.0)
    await _seed_battle(gm_client, magnus["id"], magnus["name"])
    yield magnus, krieger
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )


async def _cast(gm_client, magnus, krieger, slot_level):
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hex",
        json={
            "character_id": magnus["id"],
            "target_character_id": krieger["id"],
            "slot_level": slot_level,
            "ability": "STR",
            "override": True,
        },
    )


async def _hex_buff(gm_client, char_id):
    buffs = await _get_buffs(gm_client, char_id)
    return next(
        (b for b in buffs if (b or {}).get("key") == "hex"),
        None,
    )


async def test_hex_l1_routes_1h_duration(gm_client, magnus_armed):
    """v2.405.1: cast at L1 → substrate returns 600 rounds (1 hour); the
    `duration_label` on the installed buff resolves to "1h". Lower-tier
    branch of the substrate."""
    magnus, krieger = magnus_armed
    resp = await _cast(gm_client, magnus, krieger, slot_level=1)
    assert resp.status_code == 200, resp.text
    buff = await _hex_buff(gm_client, magnus["id"])
    assert buff is not None, "Hex buff should install"
    assert buff.get("duration_label") == "1h", \
        f"L1 should land 1h tier, got {buff.get('duration_label')!r}"


async def test_hex_l3_routes_8h_duration(gm_client, magnus_armed):
    """v2.405.1: cast at L3 → substrate returns 4800 rounds (8 hours);
    label resolves to "8h". Middle-tier branch."""
    magnus, krieger = magnus_armed
    resp = await _cast(gm_client, magnus, krieger, slot_level=3)
    assert resp.status_code == 200, resp.text
    buff = await _hex_buff(gm_client, magnus["id"])
    assert buff is not None
    assert buff.get("duration_label") == "8h", \
        f"L3 should land 8h tier, got {buff.get('duration_label')!r}"


async def test_hex_l5_routes_24h_duration(gm_client, magnus_armed):
    """v2.405.1: cast at L5 → substrate returns 14400 rounds (24 hours);
    label resolves to "24h". Upper-tier branch."""
    magnus, krieger = magnus_armed
    resp = await _cast(gm_client, magnus, krieger, slot_level=5)
    assert resp.status_code == 200, resp.text
    buff = await _hex_buff(gm_client, magnus["id"])
    assert buff is not None
    assert buff.get("duration_label") == "24h", \
        f"L5 should land 24h tier, got {buff.get('duration_label')!r}"
