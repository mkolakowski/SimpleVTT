"""Tongues — L3 divination, Bard/Cleric/Sorcerer/Warlock/Wizard.
Phase 2 #4 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.445.0 — RAW PHB p.284: "This spell grants the creature you touch
the ability to understand any spoken language it hears. Moreover,
when the target speaks, any creature that knows at least one
language and can hear the target understands what it says." Action,
V/M, Touch, 1 hour, non-concentration.

Universal-speech flag buff — same shape as Speak with Animals
(v2.438.0) but for any language, not just beast-speech. The buff's
`effects.tongues: True` flag IS the mechanic; GMs read it to know
the target understands and is understood by any language-speaker
in earshot. No engine hook needed.

Caster: Thalindra Moonwhisper (Wizard) is the canonical caster.

Tests:
  - Cast self-targets installs the buff with tongues: true.
  - The installed buff carries duration_rounds=600 + concentration=false.
  - Krieger Stonefist (Barbarian) → 409 cannot_cast.
"""
from .conftest import CAMPAIGN_ID


async def _set_battle(gm_client, caster):
    pc_cb = {
        "id": f"tok_t_caster_{caster['id']}",
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


async def _get_caster_buffs(gm_client, caster_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caster_id}/buffs",
    )
    assert r.status_code == 200, r.text
    return r.json().get("buffs") or []


async def _find_tongues_caster(roster):
    for name in (
        "Thalindra Moonwhisper",   # Wizard
        "Brother Tavik Stonebrow", # Cleric
    ):
        if name in roster:
            return roster[name]
    return None


async def test_cast_tongues_installs_buff(gm_client, roster):
    """A Wizard self-targets Tongues; the installed buff carries
    effects.tongues = true."""
    caster = await _find_tongues_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Bard/Cleric/Sorcerer/Warlock/Wizard in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_tongues",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "tongues"
    assert body["buff_installed"] is True
    assert body["target_character_id"] == caster["id"]
    assert body["duration_rounds"] == 600

    buffs = await _get_caster_buffs(gm_client, caster["id"])
    t_buff = next(
        (b for b in buffs if b.get("key") == "tongues"), None,
    )
    assert t_buff is not None, f"tongues buff missing: {buffs}"
    effects = t_buff.get("effects") or {}
    assert effects.get("tongues") is True


async def test_cast_tongues_buff_is_1_hour_non_concentration(
    gm_client, roster,
):
    """The installed buff carries duration_rounds=600 (1 hour) and
    concentration=false, matching RAW."""
    caster = await _find_tongues_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Bard/Cleric/Sorcerer/Warlock/Wizard in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_tongues",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    buffs = await _get_caster_buffs(gm_client, caster["id"])
    t_buff = next(
        (b for b in buffs if b.get("key") == "tongues"), None,
    )
    assert t_buff is not None
    assert t_buff.get("concentration") is False
    assert int(t_buff.get("duration_rounds") or 0) == 600


async def test_cast_tongues_non_caster_rejected(gm_client, roster):
    """Krieger Stonefist is a Barbarian — not in
    Bard/Cleric/Sorcerer/Warlock/Wizard. Returns 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, krieger)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_tongues",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["error"] == "cannot_cast"
    assert "tongues" in body["expected"].lower()
