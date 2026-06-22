"""Arcane Eye — L4 divination, Cleric/Wizard.
Phase 2 #63 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.549.0 — RAW PHB p.213: "You create an invisible, magical eye within
range that hovers in the air for the duration. You mentally receive
visual information from the eye, which has normal vision and darkvision
out to 30 feet. ... As an action, you can move the eye up to 30 feet in
any direction." 30 ft, Concentration up to 1 hour. The L4, 1-hour
movable sibling of Clairvoyance on the shared `_do_cast_scry_sensor`
helper (no seeing/hearing mode).

Tests:
  - Self-cast installs a concentration `arcane-eye` buff carrying
    scry_sensor_active + location, no scry_mode (600 rounds).
  - A named location surfaces.
  - Concentration ride: casting Fly drops the eye.
  - Non-caster (Barbarian) → 409; missing character_id → 400.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _tok(char, tid=None, init=10):
    return {
        "id": tid or f"tok_ae_{char['id']}",
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
        for key in ("arcane-eye", "fly"):
            await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/end_buff",
                json={"character_id": thal["id"], "key": key},
            )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [], "turn_index": 0, "round": 1, "active": False},
    )


async def test_cast_arcane_eye_installs_concentration_buff(gm_client, roster):
    """Self-cast → concentration `arcane-eye` buff with default
    location, no mode; response flags concentration, 600 rounds."""
    thal = roster["Thalindra Moonwhisper"]
    await _set_battle(gm_client, [_tok(thal)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_arcane_eye",
        json={"character_id": thal["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "arcane-eye"
    assert body["concentration"] is True
    assert body["duration_rounds"] == 600
    assert body["location"] == "within 30 ft of you"
    assert "mode" not in body  # Arcane Eye has no seeing/hearing choice

    buffs = await _buffs(gm_client, thal["id"])
    ae = next((b for b in buffs if b.get("key") == "arcane-eye"), None)
    assert ae is not None, f"buff missing: {buffs}"
    assert ae.get("concentration") is True
    eff = ae.get("effects") or {}
    assert eff.get("scry_sensor_active") is True
    assert "scry_mode" not in eff


async def test_cast_arcane_eye_named_location(gm_client, roster):
    """A named location surfaces on response + buff."""
    thal = roster["Thalindra Moonwhisper"]
    await _set_battle(gm_client, [_tok(thal)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_arcane_eye",
        json={"character_id": thal["id"], "location": "the corridor ahead"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["location"] == "the corridor ahead"
    buffs = await _buffs(gm_client, thal["id"])
    ae = next((b for b in buffs if b.get("key") == "arcane-eye"), None)
    assert (ae.get("effects") or {}).get("scry_location") == "the corridor ahead"


async def test_arcane_eye_drops_on_new_concentration(gm_client, roster):
    """Concentration ride: casting Fly drops the Arcane Eye."""
    thal = roster["Thalindra Moonwhisper"]
    await _set_battle(gm_client, [_tok(thal)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_arcane_eye",
        json={"character_id": thal["id"]},
    )
    assert r.status_code == 200, r.text
    assert any(b.get("key") == "arcane-eye"
               for b in await _buffs(gm_client, thal["id"]))

    f = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_fly",
        json={"character_id": thal["id"]},
    )
    assert f.status_code == 200, f.text
    after = await _buffs(gm_client, thal["id"])
    assert not any(x.get("key") == "arcane-eye" for x in after), after
    assert any(x.get("key") == "fly" for x in after), after


async def test_cast_arcane_eye_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, [_tok(krieger)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_arcane_eye",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "cannot_cast"
    assert "arcane eye" in r.json()["expected"].lower()


async def test_cast_arcane_eye_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_arcane_eye",
        json={},
    )
    assert r.status_code == 400, r.text
