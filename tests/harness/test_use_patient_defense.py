"""Monk Patient Defense — class feature endpoint.

v2.49.112 — adds ``POST /api/campaign/{cid}/use_patient_defense``.
Monk Lv 2+ feature: spend 1 ki as a bonus action to install the
Dodging buff on self. Lasts until start of next turn.

Tests:
  - Happy path: Kael (Monk Lv 5) uses Patient Defense; ki -1 + buff
    installed + bonus chip marked + response 200.
  - 409 wrong_class: Krieger (Barbarian) → wrong_class error.
  - 409 no_ki: drain Kael's ki to 0; next call → no_ki + ki unchanged.
  - 409 over_budget: bonus slot already used → over_budget; with
    override:true the slot gets re-used (player-side).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def kael_rested(gm_client, roster):
    kael = roster["Kael Brightleaf"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{kael['id']}/rest",
        json={"type": "long"},
    )
    return kael


async def _seed_kael_solo(gm_client, kael, *, bonus_used=False):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [{
                "id": f"tok_pd_{kael['id']}",
                "char_id": kael["id"],
                "name": kael["name"],
                "initiative": 10,
                "hp_current": 30, "hp_max": 30,
                "buffs": [],
                "economy": {"action": False, "bonus": bonus_used, "reaction": False, "movement": 0},
            }],
            "turn_index": 0, "round": 1, "active": True,
        },
    )


async def test_patient_defense_happy_path(gm_client, gm_ws, kael_rested):
    kael = kael_rested
    await _seed_kael_solo(gm_client, kael)
    gm_ws.mark()  # flush the seed-battle broadcast
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_patient_defense",
        json={"character_id": kael["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["duration_rounds"] == 1
    assert body["buff_installed"] is True
    # Ki decremented by 1. v2.49.227: Kael bumped to Lv 6 Monk → Ki max 6.
    assert body["max"] == 6
    assert body["remaining"] == 5
    # ``_install_buff`` broadcasts ``buff_update`` (not battle_update).
    bu = await gm_ws.wait_for("buff_update", timeout=2.0)
    data = bu.get("data") or {}
    assert data.get("character_id") == kael["id"]
    buffs = data.get("buffs") or []
    pd_buffs = [b for b in buffs if (b or {}).get("key") == "patient-defense"]
    assert pd_buffs, f"Patient Defense buff missing; got {buffs}"
    buff = pd_buffs[0]
    assert buff["name"] == "Patient Defense (Dodging)"
    assert buff["concentration"] is False
    assert buff["duration_rounds"] == 1
    # The effects.dodging flag is what the (B) roll-time intercept
    # reads to grant disadvantage on incoming attacks.
    eff = buff.get("effects") or {}
    assert eff.get("dodging") is True
    assert "dex_save" in (eff.get("advantage_on") or [])


async def test_patient_defense_wrong_class(gm_client, roster):
    krieger = roster["Krieger Stonefist"]
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [{
                "id": f"tok_pd_wrong_{krieger['id']}",
                "char_id": krieger["id"],
                "name": krieger["name"],
                "initiative": 10,
                "hp_current": 55, "hp_max": 55,
                "buffs": [],
                "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
            }],
            "turn_index": 0, "round": 1, "active": True,
        },
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_patient_defense",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    err = r.json()
    assert err["error"] == "wrong_class"
    assert err["expected"] == "monk"


async def test_patient_defense_no_ki(gm_client, kael_rested):
    kael = kael_rested
    await _seed_kael_solo(gm_client, kael)
    # Drain ki by repeated PD calls with override (bonus slot would
    # otherwise gate on second call). v2.49.227: Kael bumped to Lv 6 →
    # Ki max 6, so 6 successful drains → ki=0; 7th → 409 no_ki.
    for _ in range(6):
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_patient_defense",
            json={"character_id": kael["id"], "override": True},
        )
        assert r.status_code == 200, r.text
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_patient_defense",
        json={"character_id": kael["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    err = r.json()
    assert err["error"] == "no_ki"
    assert err["available"] == 0


# NOTE: the v2.49.55 / v2.49.57 Monk endpoints all gate the bonus
# slot via _is_slot_used + the user_is_gm bypass — a GM caster on
# their own Monk skips the gate. Kael (the demo Monk) is GM-owned,
# so an `over_budget` regression test would need a non-GM-owned
# Monk fixture. Filed for the harness Phase 1.5 test-fixture work;
# until then the gate is exercised end-to-end via the existing
# `test_attack.py` over-budget cases on PC weapon attacks.
