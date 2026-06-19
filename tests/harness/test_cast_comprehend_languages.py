"""Comprehend Languages — L1 divination ritual, Bard/Sorcerer/
Warlock/Wizard. Phase 2 #8 of
``docs/plans/cast-and-broadcast-tail.md``.

v2.450.0 — RAW PHB p.224: "For the duration, you understand the
literal meaning of any spoken language that you hear. You also
understand any written language that you see, but you must be
touching the surface on which the words are written." 1 action /
ritual, V/S/M, Self, 1 hour, non-concentration.

Same flag-buff shape as Tongues (v2.445.0) but understand-only
(not speak-also) and self-targeted. The flag IS the mechanic; the
GM narrates literal-meaning translation when the buff is active.

Tests:
  - Cast installs the buff with comprehends_languages: true.
  - Buff carries duration_rounds=600 + concentration=false.
  - Krieger (Barbarian) → 409 cannot_cast.
"""
from .conftest import CAMPAIGN_ID


async def _set_battle(gm_client, caster):
    pc_cb = {
        "id": f"tok_cl_caster_{caster['id']}",
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


async def _find_cl_caster(roster):
    for name in (
        "Thalindra Moonwhisper",   # Wizard
        "Lyra Sunstrider",         # Bard
    ):
        if name in roster:
            return roster[name]
    return None


async def test_cast_comprehend_languages_installs_buff(gm_client, roster):
    """A Wizard self-targets Comprehend Languages; the installed buff
    carries effects.comprehends_languages = true."""
    caster = await _find_cl_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Bard/Sorcerer/Warlock/Wizard in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_comprehend_languages",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "comprehend-languages"
    assert body["buff_installed"] is True
    assert body["duration_rounds"] == 600

    buffs = await _get_caster_buffs(gm_client, caster["id"])
    cl_buff = next(
        (b for b in buffs if b.get("key") == "comprehend-languages"), None,
    )
    assert cl_buff is not None, (
        f"comprehend-languages buff missing: {buffs}"
    )
    effects = cl_buff.get("effects") or {}
    assert effects.get("comprehends_languages") is True


async def test_cast_comprehend_languages_buff_is_1_hour_non_concentration(
    gm_client, roster,
):
    """The installed buff carries duration_rounds=600 (1 hour) and
    concentration=false, matching RAW."""
    caster = await _find_cl_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Bard/Sorcerer/Warlock/Wizard in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_comprehend_languages",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    buffs = await _get_caster_buffs(gm_client, caster["id"])
    cl_buff = next(
        (b for b in buffs if b.get("key") == "comprehend-languages"), None,
    )
    assert cl_buff is not None
    assert cl_buff.get("concentration") is False
    assert int(cl_buff.get("duration_rounds") or 0) == 600


async def test_cast_comprehend_languages_non_caster_rejected(
    gm_client, roster,
):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, krieger)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_comprehend_languages",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["error"] == "cannot_cast"
    assert "comprehend languages" in body["expected"].lower()
