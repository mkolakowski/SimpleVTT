"""v2.99.111 — Slow install-time repeated-save stamps.

Extends the v2.99.110 Hold spells pattern to /cast_slow: stamps
`repeated_save_ability: "WIS"` + `repeated_save_dc: <caster's
spell save DC>` on the slow buff so the v2.97.62 end-of-turn
auto-fire framework rolls the target's WIS save each turn. RAW:
"A creature affected by this spell makes a new Wisdom saving
throw at the end of each of its turns."

Tests:
  - Thalindra casts Slow on Krieger; slow buff carries WIS + DC>0
  - /use_repeated_save endpoint can be triggered against the buff
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


async def _get_buffs(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    assert resp.status_code == 200, resp.text
    return resp.json().get("buffs") or []


async def test_slow_stamps_repeated_save_fields(gm_client, roster):
    """Thalindra casts Slow on Krieger → slow buff with WIS + DC>0."""
    thalindra = roster["Thalindra Moonwhisper"]
    krieger = roster["Krieger Stonefist"]
    th_tok = f"tok_slow_eot_th_{thalindra['id']}"
    kr_tok = f"tok_slow_eot_kr_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(th_tok, thalindra["id"], name=thalindra["name"], speed_walk=30),
        _mkc(kr_tok, krieger["id"], name=krieger["name"], speed_walk=40),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_slow",
        json={
            "character_id": thalindra["id"],
            "class_slug": "wizard",
            "slot_level": 3,
            "target_combatant_ids": [kr_tok],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text

    buffs = await _get_buffs(gm_client, krieger["id"])
    slow = next((b for b in buffs if b.get("key") == "slow"), None)
    assert slow is not None, f"no slow buff; got {buffs}"
    assert slow.get("repeated_save_ability") == "WIS", slow
    dc = slow.get("repeated_save_dc")
    assert isinstance(dc, int) and dc > 0, slow


async def test_slow_use_repeated_save_endpoint_callable(gm_client, roster):
    """After casting Slow, /use_repeated_save can be triggered on
    Krieger against the `slow` key. Proxy for the v2.97.62 auto-fire
    framework finding + resolving the buff.
    """
    thalindra = roster["Thalindra Moonwhisper"]
    krieger = roster["Krieger Stonefist"]
    th_tok = f"tok_slow_urs_th_{thalindra['id']}"
    kr_tok = f"tok_slow_urs_kr_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(th_tok, thalindra["id"], name=thalindra["name"], speed_walk=30),
        _mkc(kr_tok, krieger["id"], name=krieger["name"], speed_walk=40),
    ])
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_slow",
        json={
            "character_id": thalindra["id"],
            "class_slug": "wizard",
            "slot_level": 3,
            "target_combatant_ids": [kr_tok],
            "override": True,
        },
    )
    save_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_repeated_save",
        json={"character_id": krieger["id"], "buff_key": "slow"},
    )
    assert save_resp.status_code == 200, save_resp.text
