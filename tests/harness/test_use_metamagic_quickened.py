"""v2.649.0 — Metamagic Quickened Spell (Sorcerer Lv 3+), the 8th + final
PHB metamagic.

RAW (PHB p.102): "When you cast a spell that has a casting time of 1
action, you can spend 2 sorcery points to change the casting time to 1
bonus action for this casting." `/use_metamagic_quickened_spell` spends
2 SP + arms a `metamagic-quickened-pending` buff; the next `/cast_spell`
of a 1-action spell reads it (`_caster_has_quickened_pending`), retargets
the economy slot to `bonus`, and consumes the buff.

Tests:
  - arm: 2 SP decrement + armed broadcast + buff installed.
  - consume: cast a 1-action spell with it armed → bonus slot marked
    (not action) + consumed broadcast + buff dropped.
  - wrong class → 409.
"""
import asyncio

import pytest_asyncio

from .conftest import CAMPAIGN_ID


HOLD_PERSON_ZARA_INDEX = 13


@pytest_asyncio.fixture
async def zara_rested(gm_client, roster):
    zara = roster["Zara Emberfire"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/rest",
        json={"type": "long"},
    )
    return zara


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


def _tok(char):
    return {
        "id": f"tok_qk_{char['id']}", "char_id": char["id"],
        "name": char["name"], "initiative": 10,
        "hp_current": 30, "hp_max": 30, "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _buff_keys(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    return {(b or {}).get("key") for b in resp.json().get("buffs") or []}


async def test_quickened_arms_buff_and_decrements_sp(
    gm_client, gm_ws, zara_rested,
):
    zara = zara_rested
    await _seed_battle(gm_client, [_tok(zara)])
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_quickened_spell",
        json={"character_id": zara["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["sp_cost"] == 2
    assert data["sp_remaining"] == data["sp_max"] - 2
    await asyncio.sleep(0.15)
    armed = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source")
        == "metamagic-quickened-spell-armed"
    ]
    assert armed, "expected an armed broadcast"
    assert "metamagic-quickened-pending" in await _buff_keys(
        gm_client, zara["id"],
    )


async def test_quickened_cast_uses_bonus_slot_and_consumes(
    gm_client, gm_ws, zara_rested, roster,
):
    zara = zara_rested
    pip = roster["Pip Quickfingers"]
    await _seed_battle(gm_client, [_tok(zara), _tok(pip)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_quickened_spell",
        json={"character_id": zara["id"]},
    )
    assert r.status_code == 200, r.text
    await asyncio.sleep(0.1)
    gm_ws.mark()
    c = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": zara["id"],
            "spell_index": HOLD_PERSON_ZARA_INDEX,
            "slot_level": 2, "class_slug": "sorcerer",
            "target_combatant_id": f"tok_qk_{pip['id']}",
            "target_character_id": pip["id"], "target_name": pip["name"],
            "override": True,
        },
    )
    assert c.status_code == 200, c.text
    await asyncio.sleep(0.15)
    econ = [
        m for m in gm_ws.buffered("economy_update")
        if (m.get("data") or {}).get("character_id") == zara["id"]
    ]
    bonus = [
        m for m in econ
        if (m.get("data") or {}).get("slot") == "bonus"
        and (m.get("data") or {}).get("used") is True
    ]
    action = [
        m for m in econ
        if (m.get("data") or {}).get("slot") == "action"
        and (m.get("data") or {}).get("used") is True
    ]
    assert bonus, (
        f"expected the bonus slot marked; "
        f"got {[(m.get('data') or {}).get('slot') for m in econ]}"
    )
    assert not action, "a Quickened cast must not mark the action slot"
    consumed = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source")
        == "metamagic-quickened-spell-consumed"
    ]
    assert consumed, "expected a quickened-consumed broadcast"
    assert "metamagic-quickened-pending" not in await _buff_keys(
        gm_client, zara["id"],
    ), "the pending buff should be consumed"


async def test_quickened_wrong_class(gm_client, roster):
    pip = roster["Pip Quickfingers"]  # Rogue
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_quickened_spell",
        json={"character_id": pip["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json().get("error") == "wrong_class"
