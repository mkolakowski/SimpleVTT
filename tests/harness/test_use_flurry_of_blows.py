"""Monk Flurry of Blows — class feature endpoint.

v2.49.114 — adds ``POST /api/campaign/{cid}/use_flurry_of_blows``.
Monk Lv 2+: spend 1 ki as a bonus action to install the
``flurry-of-blows-active`` buff (1-round). Effects field carries
``unarmed_strikes_available: 2`` + ``is_flurry: True`` — signal a
future commit will read to (a) refund the attack chip for the
next two unarmed strikes and (b) gate the v2.49.57 Open Hand
Technique trigger.

Tests:
  - Happy path: Kael (Monk Lv 5) → ki -1, buff installed, 200.
  - 409 wrong_class: Krieger (Barbarian) → wrong_class.
  - 409 no_ki: drain ki to 0; next call → no_ki.
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


async def _seed_kael_solo(gm_client, kael):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [{
                "id": f"tok_fob_{kael['id']}",
                "char_id": kael["id"],
                "name": kael["name"],
                "initiative": 10,
                "hp_current": 30, "hp_max": 30,
                "buffs": [],
                "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
            }],
            "turn_index": 0, "round": 1, "active": True,
        },
    )


async def test_flurry_of_blows_happy_path(gm_client, gm_ws, kael_rested):
    kael = kael_rested
    await _seed_kael_solo(gm_client, kael)
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_flurry_of_blows",
        json={"character_id": kael["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["unarmed_strikes_available"] == 2
    assert body["remaining"] == 6  # Kael's max ki is 7 at Lv 7 (v2.49.229)
    assert body["buff_installed"] is True
    bu = await gm_ws.wait_for("buff_update", timeout=2.0)
    data = bu.get("data") or {}
    assert data.get("character_id") == kael["id"]
    buffs = data.get("buffs") or []
    fob = [b for b in buffs if (b or {}).get("key") == "flurry-of-blows-active"]
    assert fob, f"Flurry buff missing; got {buffs}"
    buff = fob[0]
    eff = buff.get("effects") or {}
    assert eff.get("unarmed_strikes_available") == 2
    assert eff.get("is_flurry") is True
    assert buff["concentration"] is False
    assert buff["duration_rounds"] == 1


async def test_flurry_of_blows_wrong_class(gm_client, roster):
    krieger = roster["Krieger Stonefist"]
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [{
                "id": f"tok_fob_wrong_{krieger['id']}",
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
        f"/api/campaign/{CAMPAIGN_ID}/use_flurry_of_blows",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    err = r.json()
    assert err["error"] == "wrong_class"
    assert err["expected"] == "monk"


async def test_flurry_of_blows_no_ki(gm_client, kael_rested):
    kael = kael_rested
    await _seed_kael_solo(gm_client, kael)
    # v2.49.229: Kael bumped to Lv 7 → Ki max 7; drain takes 7 calls.
    for _ in range(7):
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_flurry_of_blows",
            json={"character_id": kael["id"], "override": True},
        )
        assert r.status_code == 200, r.text
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_flurry_of_blows",
        json={"character_id": kael["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    err = r.json()
    assert err["error"] == "no_ki"
    assert err["available"] == 0
