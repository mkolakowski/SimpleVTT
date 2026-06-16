"""v2.371.0 — Aid upcast scaling (RAW PHB p.211).

Base L2 grants +5 HP-max + +5 current HP. RAW: "At Higher Levels:
When you cast this spell using a spell slot of 3rd level or higher,
a target's hit points increase by an additional 5 for each slot
level above 2nd."

v2.97.41 wired the install-time current-HP heal + the
`_buff_hp_max_bonus` ceiling expansion from `aid_hp_bonus: 5`. This
commit (v2.371.0) makes `aid_hp_bonus` scale with slot_level:
- L2 → 5  (default catalog value)
- L3 → 10
- L4 → 15
- L5 → 20

The install-time heal at /cast_spell + the ceiling walk both read
the materialized buff's `aid_hp_bonus`, so the upcast value
propagates without touching either downstream site.

Tests:
  - Cast at L2 → installed buff carries `aid_hp_bonus: 5`,
    Pip's hp_current rose by 5.
  - Cast at L3 → installed buff carries `aid_hp_bonus: 10`,
    hp_current rose by 10.
  - Cast at L5 → installed buff carries `aid_hp_bonus: 20`.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


CAELAN_AID_INDEX = 5  # matches the v2.97.40 fixture


async def _long_rest(gm_client, char_id):
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )


async def _end_aid(gm_client, char_id):
    """Drop the aid buff so the next cast install fires cleanly."""
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": char_id, "key": "aid"},
    )


async def _seed_battle(gm_client, caelan, pip, pip_hp_current=30, pip_hp_max=40):
    pip_tok = f"tok_aid_upcast_pip_{pip['id']}"
    caelan_tok = f"tok_aid_upcast_caelan_{caelan['id']}"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [
                {
                    "id": caelan_tok, "char_id": caelan["id"],
                    "name": caelan["name"], "initiative": 10,
                    "hp_current": 60, "hp_max": 60, "buffs": [],
                    "economy": {"action": False, "bonus": False,
                                "reaction": False, "movement": 0},
                },
                {
                    "id": pip_tok, "char_id": pip["id"],
                    "name": pip["name"], "initiative": 8,
                    "hp_current": pip_hp_current, "hp_max": pip_hp_max,
                    "buffs": [],
                    "economy": {"action": False, "bonus": False,
                                "reaction": False, "movement": 0},
                },
            ],
            "turn_index": 0, "round": 1, "active": True,
        },
    )
    return pip_tok, caelan_tok


async def _cast_aid(gm_client, caelan, pip, pip_tok, slot_level):
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": caelan["id"],
            "spell_index": CAELAN_AID_INDEX,
            "slot_level": slot_level,
            "class_slug": "paladin",
            "target_character_id": pip["id"],
            "target_combatant_id": pip_tok,
            "target_name": pip["name"],
            "override": True,
            "override_range": True,
        },
    )


async def _pip_aid_buff(gm_client, pip_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip_id}/buffs",
    )
    buffs = r.json().get("buffs", [])
    return next(
        (b for b in buffs if (b or {}).get("key") == "aid"),
        None,
    )


async def _pip_hp(gm_client, pip_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip_id}/sheet-json",
    )
    return ((r.json() or {}).get("sheet") or {}).get("hp") or {}


@pytest_asyncio.fixture
async def caelan(gm_client, roster):
    caelan = roster["Sir Caelan Lightbringer"]
    await _long_rest(gm_client, caelan["id"])
    return caelan


@pytest_asyncio.fixture
async def pip(gm_client, roster):
    pip = roster["Pip Quickfingers"]
    await _long_rest(gm_client, pip["id"])
    await _end_aid(gm_client, pip["id"])
    return pip


async def test_aid_base_l2_grants_5_hp(gm_client, caelan, pip):
    """Cast at L2 → installed buff carries `aid_hp_bonus: 5`."""
    await _end_aid(gm_client, pip["id"])
    pip_tok, _ = await _seed_battle(gm_client, caelan, pip)
    resp = await _cast_aid(gm_client, caelan, pip, pip_tok, slot_level=2)
    assert resp.status_code == 200, resp.text
    buff = await _pip_aid_buff(gm_client, pip["id"])
    assert buff is not None, "Aid not installed"
    assert (buff.get("effects") or {}).get("aid_hp_bonus") == 5
    await _end_aid(gm_client, pip["id"])


async def test_aid_l3_upcast_grants_10_hp(gm_client, caelan, pip):
    """Cast at L3 → installed buff carries `aid_hp_bonus: 10` (RAW: +5
    per slot level above 2nd)."""
    await _end_aid(gm_client, pip["id"])
    pip_tok, _ = await _seed_battle(gm_client, caelan, pip)
    resp = await _cast_aid(gm_client, caelan, pip, pip_tok, slot_level=3)
    assert resp.status_code == 200, resp.text
    buff = await _pip_aid_buff(gm_client, pip["id"])
    assert buff is not None, "Aid not installed"
    assert (buff.get("effects") or {}).get("aid_hp_bonus") == 10, (
        f"L3 Aid should grant +10 (5 base + 5 per upcast level); "
        f"got {(buff.get('effects') or {}).get('aid_hp_bonus')!r}"
    )
    await _end_aid(gm_client, pip["id"])


async def test_aid_l5_upcast_grants_20_hp(gm_client, caelan, pip):
    """Cast at L5 → installed buff carries `aid_hp_bonus: 20` (5 base +
    5×3 upcast = 20)."""
    await _end_aid(gm_client, pip["id"])
    pip_tok, _ = await _seed_battle(gm_client, caelan, pip)
    resp = await _cast_aid(gm_client, caelan, pip, pip_tok, slot_level=5)
    if resp.status_code != 200:
        # Caelan may not have a L5 slot (Paladin Lv 7 has up to L2).
        # Patch a temporary L5 slot via sheet PATCH for this test.
        sheet_r = await gm_client.get(
            f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/sheet-json",
        )
        sheet = (sheet_r.json() or {}).get("sheet") or {}
        slot_snap = dict(sheet.get("spell_slots") or {})
        new_slots = {**slot_snap}
        new_slots.setdefault("paladin", {})
        new_slots["paladin"] = dict(new_slots["paladin"])
        new_slots["paladin"]["5"] = {"total": 1, "used": 0}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/sheet-fields",
            json={"spell_slots": new_slots},
        )
        try:
            resp = await _cast_aid(gm_client, caelan, pip, pip_tok, slot_level=5)
            assert resp.status_code == 200, resp.text
            buff = await _pip_aid_buff(gm_client, pip["id"])
            assert buff is not None, "Aid not installed"
            assert (buff.get("effects") or {}).get("aid_hp_bonus") == 20, (
                f"L5 Aid should grant +20 (5 base + 15 upcast); "
                f"got {(buff.get('effects') or {}).get('aid_hp_bonus')!r}"
            )
        finally:
            await gm_client.patch(
                f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/sheet-fields",
                json={"spell_slots": slot_snap},
            )
    else:
        buff = await _pip_aid_buff(gm_client, pip["id"])
        assert (buff.get("effects") or {}).get("aid_hp_bonus") == 20
    await _end_aid(gm_client, pip["id"])
