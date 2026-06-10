"""v2.158.62 — Demo Way of the Drunken Master Monk (Quan Reelstep) seed contract.

v2.158.61 wired the Drunken Technique sheet button (Way of the Drunken
Master Monk Lv 3+ class feature → /use_drunken_technique) into the
class-features Use button, but no demo PC was a Way of the Drunken
Master Monk — Kael Brightleaf is Way of the Open Hand, whose
class-features list has no Drunken Technique entry. This commit adds
Quan Reelstep (Way of the Drunken Master Lv 5) so the button is
reachable + verifiable in the live demo.

These tests assert the seed shape the class-features Use button depends
on, then fire /use_drunken_technique against the REAL seeded PC (no
PATCH) — unlike test_drunken_technique.py which PATCHes Kael into Way
of the Drunken Master.

Tests:
  - Seed contract: the PC exists, is Monk / Way of the Drunken Master
    Lv 5, and carries a class_features entry keyed "drunken-technique"
    (the entry the .cf-use button renders + routes from).
  - Happy path: with a battle seeded, /use_drunken_technique returns
    200, installs the buff, and broadcasts
    feature_used(source=drunken-technique).
"""
import asyncio

from .conftest import CAMPAIGN_ID

PC_NAME = "Quan Reelstep"


async def _sheet(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json"
    )
    assert r.status_code == 200, r.text
    return r.json()["sheet"]


async def test_demo_drunken_monk_seed_contract(gm_client, roster):
    """The seeded PC is a Lv 5 Way of the Drunken Master Monk carrying a
    class_features entry keyed "drunken-technique" — the exact shape the
    class-features Use button needs to render + route Drunken Technique."""
    assert PC_NAME in roster, f"{PC_NAME} missing from demo roster"
    pc = roster[PC_NAME]
    sheet = await _sheet(gm_client, pc["id"])

    assert (sheet.get("class") or "").lower() == "monk"
    assert (sheet.get("subclass") or "").lower() == "way of the drunken master"
    assert int(sheet.get("level") or 0) == 5

    feats = sheet.get("class_features") or []
    dt = next(
        (f for f in feats if (f.get("key") or "").lower() == "drunken-technique"),
        None,
    )
    assert dt is not None, (
        f"seed should carry a drunken-technique class feature; got {feats!r}"
    )


async def test_demo_drunken_monk_can_trigger_technique(gm_client, gm_ws, roster):
    """End-to-end against the real seeded PC: seed a battle, fire
    /use_drunken_technique → 200, buff installed,
    feature_used(source=drunken-technique) broadcast."""
    pc = roster[PC_NAME]
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_dm_{pc['id']}", "char_id": pc["id"], "name": pc["name"],
             "initiative": 12, "hp_current": 38, "hp_max": 38, "buffs": [],
             "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_drunken_technique",
        json={"character_id": pc["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True
    assert data["feature"] == "drunken-technique"
    assert data["disengage"] is True
    assert data["speed_bonus_ft"] == 10
    assert data["monk_level"] == 5
    assert data["buff_installed"] is True

    await asyncio.sleep(0.3)
    feats = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "drunken-technique"
        and (m.get("data") or {}).get("character_id") == pc["id"]
    ]
    assert feats, "expected a feature_used(source=drunken-technique) broadcast"
