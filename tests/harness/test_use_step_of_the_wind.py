"""Monk Step of the Wind — class feature endpoint.

v2.49.112 — adds ``POST /api/campaign/{cid}/use_step_of_the_wind``.
Monk Lv 2+ feature: spend 1 ki as a bonus action to install either
the Disengage OR Dash variant of Step of the Wind. Jump distance
doubles for the turn either way.

Tests:
  - Disengage mode happy path: ki -1, disengage buff installed.
  - Dash mode happy path: ki -1, dash buff installed.
  - 409 wrong_class.
  - 400 invalid mode.
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
                "id": f"tok_sotw_{kael['id']}",
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


async def test_step_of_the_wind_disengage_mode(gm_client, gm_ws, kael_rested):
    kael = kael_rested
    await _seed_kael_solo(gm_client, kael)
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_step_of_the_wind",
        json={"character_id": kael["id"], "mode": "disengage"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["mode"] == "disengage"
    assert body["buff_installed"] is True
    assert body["remaining"] == 6  # Kael's max ki is 7 at Lv 7 (v2.49.229)
    bu = await gm_ws.wait_for("buff_update", timeout=2.0)
    data = bu.get("data") or {}
    assert data.get("character_id") == kael["id"]
    buffs = data.get("buffs") or []
    sotw = [b for b in buffs if (b or {}).get("key") == "step-of-the-wind-disengage"]
    assert sotw, f"disengage buff missing; got {buffs}"
    buff = sotw[0]
    eff = buff.get("effects") or {}
    assert eff.get("disengage") is True
    assert eff.get("jump_distance_doubled") is True
    assert buff["concentration"] is False


async def test_step_of_the_wind_dash_mode(gm_client, gm_ws, kael_rested):
    kael = kael_rested
    await _seed_kael_solo(gm_client, kael)
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_step_of_the_wind",
        json={"character_id": kael["id"], "mode": "dash"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "dash"
    bu = await gm_ws.wait_for("buff_update", timeout=2.0)
    data = bu.get("data") or {}
    buffs = data.get("buffs") or []
    sotw = [b for b in buffs if (b or {}).get("key") == "step-of-the-wind-dash"]
    assert sotw, f"dash buff missing; got {buffs}"
    eff = sotw[0].get("effects") or {}
    assert eff.get("dash") is True
    assert eff.get("jump_distance_doubled") is True


async def test_step_of_the_wind_wrong_class(gm_client, roster):
    krieger = roster["Krieger Stonefist"]
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [{
                "id": f"tok_sotw_wrong_{krieger['id']}",
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
        f"/api/campaign/{CAMPAIGN_ID}/use_step_of_the_wind",
        json={"character_id": krieger["id"], "mode": "disengage"},
    )
    assert r.status_code == 409, r.text
    err = r.json()
    assert err["error"] == "wrong_class"
    assert err["expected"] == "monk"


async def test_step_of_the_wind_invalid_mode(gm_client, kael_rested):
    kael = kael_rested
    await _seed_kael_solo(gm_client, kael)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_step_of_the_wind",
        json={"character_id": kael["id"], "mode": "fly"},
    )
    assert r.status_code == 400, r.text
    assert "mode" in r.text.lower()
