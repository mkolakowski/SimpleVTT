"""v2.158.60 — Demo Path of the Beast Barbarian (Brakka Wildmane) seed contract.

v2.158.59 wired the Form of the Beast sheet button (Path of the Beast
Barbarian Lv 3+ class feature → /use_form_of_the_beast) into the
class-features Use button, but no demo PC was a Path of the Beast
Barbarian — Krieger Stonefist is Path of the Berserker, whose
class-features list has no Form of the Beast entry. This commit adds
Brakka Wildmane (Path of the Beast Lv 5) so the button is reachable +
verifiable in the live demo.

These tests assert the seed shape the class-features Use button depends
on, then fire /use_form_of_the_beast against the REAL seeded PC (no
PATCH) — unlike test_form_of_the_beast.py which PATCHes Krieger into
Path of the Beast.

Tests:
  - Seed contract: the PC exists, is Barbarian / Path of the Beast Lv 5,
    and carries a class_features entry keyed "form-of-the-beast" (the
    entry the .cf-use button renders + routes from).
  - Happy path: with a battle seeded, /use_form_of_the_beast (form
    "claws") returns 200, installs the buff, and broadcasts
    feature_used(source=form-of-the-beast).
"""
import asyncio

from .conftest import CAMPAIGN_ID

PC_NAME = "Brakka Wildmane"


async def _sheet(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json"
    )
    assert r.status_code == 200, r.text
    return r.json()["sheet"]


async def test_demo_beast_barbarian_seed_contract(gm_client, roster):
    """The seeded PC is a Lv 5 Path of the Beast Barbarian carrying a
    class_features entry keyed "form-of-the-beast" — the exact shape the
    class-features Use button needs to render + route Form of the Beast."""
    assert PC_NAME in roster, f"{PC_NAME} missing from demo roster"
    pc = roster[PC_NAME]
    sheet = await _sheet(gm_client, pc["id"])

    assert (sheet.get("class") or "").lower() == "barbarian"
    assert (sheet.get("subclass") or "").lower() == "path of the beast"
    assert int(sheet.get("level") or 0) == 5

    feats = sheet.get("class_features") or []
    fotb = next(
        (f for f in feats if (f.get("key") or "").lower() == "form-of-the-beast"),
        None,
    )
    assert fotb is not None, (
        f"seed should carry a form-of-the-beast class feature; got {feats!r}"
    )


async def test_demo_beast_barbarian_can_manifest_form(gm_client, gm_ws, roster):
    """End-to-end against the real seeded PC: seed a battle, fire
    /use_form_of_the_beast (claws) → 200, buff installed,
    feature_used(source=form-of-the-beast) broadcast."""
    pc = roster[PC_NAME]
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_bb_{pc['id']}", "char_id": pc["id"], "name": pc["name"],
             "initiative": 12, "hp_current": 55, "hp_max": 55, "buffs": [],
             "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_form_of_the_beast",
        json={"character_id": pc["id"], "form": "claws"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True
    assert data["form"] == "claws"
    assert data["damage_die"] == "1d6"
    assert data["buff_installed"] is True

    await asyncio.sleep(0.3)
    feats = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "form-of-the-beast"
        and (m.get("data") or {}).get("character_id") == pc["id"]
    ]
    assert feats, "expected a feature_used(source=form-of-the-beast) broadcast"
