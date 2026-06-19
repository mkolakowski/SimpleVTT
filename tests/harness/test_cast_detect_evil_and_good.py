"""Detect Evil and Good — L1 divination, Cleric/Paladin.
Phase 2 #13 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.456.0 — RAW PHB p.231: "For the duration, you know if there
is an aberration, celestial, elemental, fey, fiend, or undead
within 30 feet of you, as well as where the creature is located.
Similarly, you know if there is a place or object within 30 feet
of you that has been magically consecrated or desecrated." 1
action, V/S, Self, Concentration up to 10 minutes.

New ``_SPELL_BUFF_MAP["detect-evil-and-good"]`` substrate
carrying ``effects.senses_evil_and_good_within_30ft: True`` —
flag-buff shape (same as Tongues v2.445.0 / Comprehend Languages
v2.450.0 / Jump v2.453.0): the flag IS the mechanic, the GM
narrates what the caster senses.

Tests:
  - Cast self-installs buff with
    senses_evil_and_good_within_30ft: true.
  - Buff carries duration_rounds=100 + concentration=true.
  - Cleric (Tavik) and Paladin gates: Tavik should succeed.
  - Krieger (Barbarian) → 409 cannot_cast.
"""
from .conftest import CAMPAIGN_ID


async def _set_battle(gm_client, caster):
    pc_cb = {
        "id": f"tok_deg_caster_{caster['id']}",
        "char_id": caster["id"],
        "name": caster["name"],
        "initiative": 15,
        "hp_current": 30, "hp_max": 30,
        "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [pc_cb], "turn_index": 0,
              "round": 1, "active": True},
    )


async def _get_buffs(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    assert r.status_code == 200, r.text
    return r.json().get("buffs") or []


async def test_cast_deg_installs_buff(gm_client, roster):
    """A Cleric self-casts Detect Evil and Good; the installed buff
    carries effects.senses_evil_and_good_within_30ft = true."""
    cleric = roster["Brother Tavik Stonebrow"]
    await _set_battle(gm_client, cleric)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_detect_evil_and_good",
        json={"character_id": cleric["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "detect-evil-and-good"
    assert body["buff_installed"] is True
    assert body["duration_rounds"] == 100

    buffs = await _get_buffs(gm_client, cleric["id"])
    deg_buff = next(
        (b for b in buffs
         if b.get("key") == "detect-evil-and-good"), None,
    )
    assert deg_buff is not None, (
        f"detect-evil-and-good buff missing: {buffs}"
    )
    effects = deg_buff.get("effects") or {}
    assert effects.get("senses_evil_and_good_within_30ft") is True


async def test_cast_deg_buff_is_10_min_concentration(gm_client, roster):
    """The installed buff carries duration_rounds=100 (10 minutes)
    and concentration=true, matching RAW."""
    cleric = roster["Brother Tavik Stonebrow"]
    await _set_battle(gm_client, cleric)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_detect_evil_and_good",
        json={"character_id": cleric["id"]},
    )
    assert r.status_code == 200, r.text
    buffs = await _get_buffs(gm_client, cleric["id"])
    deg_buff = next(
        (b for b in buffs
         if b.get("key") == "detect-evil-and-good"), None,
    )
    assert deg_buff is not None
    assert deg_buff.get("concentration") is True
    assert int(deg_buff.get("duration_rounds") or 0) == 100


async def test_cast_deg_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast — Detect Evil and Good
    is Cleric/Paladin only, not Bard/Druid/Wizard."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, krieger)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_detect_evil_and_good",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["error"] == "cannot_cast"
    assert "detect evil and good" in body["expected"].lower()


async def test_cast_deg_wizard_rejected(gm_client, roster):
    """Wizards are NOT on the Detect Evil and Good class list per
    RAW (Cleric/Paladin only). Thalindra → 409."""
    wiz = roster["Thalindra Moonwhisper"]
    await _set_battle(gm_client, wiz)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_detect_evil_and_good",
        json={"character_id": wiz["id"]},
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["error"] == "cannot_cast"
