"""Clairvoyance — L3 divination, Bard/Cleric/Sorcerer/Warlock/Wizard.
Phase 2 #62 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.548.0 — RAW PHB p.221: "You create an invisible sensor within range
in a location familiar to you ... You can choose seeing or hearing." 1
mile, Concentration up to 10 minutes. A scrying-sensor flag-buff on the
shared `_do_cast_scry_sensor` helper — the sensor's view is GM-narrated,
the concentration ride is mechanical.

Tests:
  - Self-cast installs a concentration `clairvoyance` buff carrying
    scry_sensor_active + location + mode "seeing" (100 rounds).
  - mode "hearing" + a named location surface.
  - Concentration ride: casting Fly drops the sensor.
  - Non-caster (Barbarian) → 409; missing character_id → 400.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _tok(char, tid=None, init=10):
    return {
        "id": tid or f"tok_cl_{char['id']}",
        "char_id": char["id"],
        "name": char["name"],
        "initiative": init,
        "hp_current": 40, "hp_max": 40,
        "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _set_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


async def _buffs(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    assert r.status_code == 200, r.text
    return r.json().get("buffs") or []


@pytest_asyncio.fixture(autouse=True)
async def _cleanup(gm_client, roster):
    yield
    thal = roster.get("Thalindra Moonwhisper")
    if thal:
        for key in ("clairvoyance", "fly"):
            await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/end_buff",
                json={"character_id": thal["id"], "key": key},
            )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [], "turn_index": 0, "round": 1, "active": False},
    )


async def test_cast_clairvoyance_installs_concentration_buff(gm_client, roster):
    """Self-cast → concentration `clairvoyance` buff with default
    location + mode "seeing"; response flags concentration."""
    thal = roster["Thalindra Moonwhisper"]
    await _set_battle(gm_client, [_tok(thal)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_clairvoyance",
        json={"character_id": thal["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "clairvoyance"
    assert body["concentration"] is True
    assert body["duration_rounds"] == 100
    assert body["mode"] == "seeing"
    assert body["location"] == "a familiar location"

    buffs = await _buffs(gm_client, thal["id"])
    cl = next((b for b in buffs if b.get("key") == "clairvoyance"), None)
    assert cl is not None, f"buff missing: {buffs}"
    assert cl.get("concentration") is True
    eff = cl.get("effects") or {}
    assert eff.get("scry_sensor_active") is True
    assert eff.get("scry_mode") == "seeing"


async def test_cast_clairvoyance_hearing_mode_and_location(gm_client, roster):
    """mode "hearing" + a named location surface on response + buff."""
    thal = roster["Thalindra Moonwhisper"]
    await _set_battle(gm_client, [_tok(thal)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_clairvoyance",
        json={"character_id": thal["id"], "mode": "hearing",
              "location": "the war room"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "hearing"
    assert body["location"] == "the war room"
    buffs = await _buffs(gm_client, thal["id"])
    cl = next((b for b in buffs if b.get("key") == "clairvoyance"), None)
    eff = cl.get("effects") or {}
    assert eff.get("scry_mode") == "hearing"
    assert eff.get("scry_location") == "the war room"


async def test_clairvoyance_drops_on_new_concentration(gm_client, roster):
    """Concentration ride: casting Fly drops the Clairvoyance sensor."""
    thal = roster["Thalindra Moonwhisper"]
    await _set_battle(gm_client, [_tok(thal)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_clairvoyance",
        json={"character_id": thal["id"]},
    )
    assert r.status_code == 200, r.text
    assert any(b.get("key") == "clairvoyance"
               for b in await _buffs(gm_client, thal["id"]))

    f = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_fly",
        json={"character_id": thal["id"]},
    )
    assert f.status_code == 200, f.text
    after = await _buffs(gm_client, thal["id"])
    assert not any(x.get("key") == "clairvoyance" for x in after), after
    assert any(x.get("key") == "fly" for x in after), after


async def test_cast_clairvoyance_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, [_tok(krieger)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_clairvoyance",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "cannot_cast"
    assert "clairvoyance" in r.json()["expected"].lower()


async def test_cast_clairvoyance_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_clairvoyance",
        json={},
    )
    assert r.status_code == 400, r.text
