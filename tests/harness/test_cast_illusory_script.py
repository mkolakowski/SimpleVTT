"""Illusory Script — L1 illusion, Bard/Warlock/Wizard.
Phase 2 #66 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.552.0 — RAW PHB p.252: "You write on parchment ... and imbue it with
a potent illusion that lasts for the duration. To you and any creatures
you designate ... the writing appears normal ... To all others the
writing appears as ... unintelligible text." Touch, 10 days,
non-concentration. The L1, 10-day sibling of Magic Mouth on the shared
`_do_cast_inscribed_illusion` helper — who can read it + the
gibberish-to-others illusion are GM-narrated.

Tests:
  - Self-cast installs a non-concentration `illusory-script` buff with
    default message + readers; response reports "10 days".
  - A named message + readers surface.
  - Non-caster (Barbarian) → 409; missing character_id → 400.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _tok(char, tid=None, init=10):
    return {
        "id": tid or f"tok_is_{char['id']}",
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
            json={"character_id": thal["id"], "key": "illusory-script"},
        )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [], "turn_index": 0, "round": 1, "active": False},
    )


async def test_cast_illusory_script_installs_ten_day_buff(gm_client, roster):
    """Self-cast → non-concentration `illusory-script` buff with default
    message + readers; response reports 10 days."""
    thal = roster["Thalindra Moonwhisper"]
    await _set_battle(gm_client, [_tok(thal)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_illusory_script",
        json={"character_id": thal["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "illusory-script"
    assert body["duration"] == "10 days"
    assert body["message"] == "(no message set)"
    assert body["readers"] == "those you designate"

    buffs = await _buffs(gm_client, thal["id"])
    isc = next((b for b in buffs if b.get("key") == "illusory-script"), None)
    assert isc is not None, f"buff missing: {buffs}"
    assert isc.get("concentration") is False
    eff = isc.get("effects") or {}
    assert eff.get("illusory_script_active") is True
    assert eff.get("illusory_script_message") == "(no message set)"
    assert eff.get("illusory_script_readers") == "those you designate"


async def test_cast_illusory_script_named_message_and_readers(gm_client, roster):
    """A named message + readers surface on response + buff."""
    thal = roster["Thalindra Moonwhisper"]
    await _set_battle(gm_client, [_tok(thal)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_illusory_script",
        json={"character_id": thal["id"],
              "message": "The vault key is under the third flagstone.",
              "readers": "the Thieves' Guild"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["message"] == "The vault key is under the third flagstone."
    assert body["readers"] == "the Thieves' Guild"
    buffs = await _buffs(gm_client, thal["id"])
    isc = next((b for b in buffs if b.get("key") == "illusory-script"), None)
    eff = isc.get("effects") or {}
    assert eff.get("illusory_script_message") == "The vault key is under the third flagstone."
    assert eff.get("illusory_script_readers") == "the Thieves' Guild"


async def test_cast_illusory_script_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, [_tok(krieger)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_illusory_script",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "cannot_cast"
    assert "illusory script" in r.json()["expected"].lower()


async def test_cast_illusory_script_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_illusory_script",
        json={},
    )
    assert r.status_code == 400, r.text
