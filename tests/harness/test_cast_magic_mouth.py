"""Magic Mouth — L2 illusion, Bard/Wizard.
Phase 2 #65 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.551.0 — RAW PHB p.259: "You implant a message within an object in
range, a message that is uttered when a trigger condition is met." 30
ft, Until dispelled, non-concentration. SimpleVTT models no objects or
trigger engine, so this records the message + trigger on a long-lived
flag-buff and broadcasts the cast; the trigger firing + playback are
GM-narrated.

Tests:
  - Self-cast installs a non-concentration `magic-mouth` buff with
    default message + trigger; response reports "until dispelled".
  - A named message + trigger surface.
  - Non-caster (Barbarian) → 409; missing character_id → 400.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _tok(char, tid=None, init=10):
    return {
        "id": tid or f"tok_mm_{char['id']}",
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
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/end_buff",
            json={"character_id": thal["id"], "key": "magic-mouth"},
        )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [], "turn_index": 0, "round": 1, "active": False},
    )


async def test_cast_magic_mouth_installs_until_dispelled_buff(gm_client, roster):
    """Self-cast → non-concentration `magic-mouth` buff with default
    message + trigger; response reports until-dispelled."""
    thal = roster["Thalindra Moonwhisper"]
    await _set_battle(gm_client, [_tok(thal)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_magic_mouth",
        json={"character_id": thal["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "magic-mouth"
    assert body["duration"] == "until dispelled"
    assert body["message"] == "(no message set)"
    assert body["trigger"] == "a set condition"

    buffs = await _buffs(gm_client, thal["id"])
    mm = next((b for b in buffs if b.get("key") == "magic-mouth"), None)
    assert mm is not None, f"buff missing: {buffs}"
    assert mm.get("concentration") is False
    eff = mm.get("effects") or {}
    assert eff.get("magic_mouth_active") is True
    assert eff.get("magic_mouth_message") == "(no message set)"
    assert eff.get("magic_mouth_trigger") == "a set condition"


async def test_cast_magic_mouth_named_message_and_trigger(gm_client, roster):
    """A named message + trigger surface on response + buff."""
    thal = roster["Thalindra Moonwhisper"]
    await _set_battle(gm_client, [_tok(thal)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_magic_mouth",
        json={"character_id": thal["id"],
              "message": "Turn back or perish!",
              "trigger": "a creature approaches within 5 feet"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["message"] == "Turn back or perish!"
    assert body["trigger"] == "a creature approaches within 5 feet"
    buffs = await _buffs(gm_client, thal["id"])
    mm = next((b for b in buffs if b.get("key") == "magic-mouth"), None)
    eff = mm.get("effects") or {}
    assert eff.get("magic_mouth_message") == "Turn back or perish!"
    assert eff.get("magic_mouth_trigger") == "a creature approaches within 5 feet"


async def test_cast_magic_mouth_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, [_tok(krieger)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_magic_mouth",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "cannot_cast"
    assert "magic mouth" in r.json()["expected"].lower()


async def test_cast_magic_mouth_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_magic_mouth",
        json={},
    )
    assert r.status_code == 400, r.text
