"""Spider Climb — L2 transmutation, Druid/Sorcerer/Warlock/Wizard.
Phase 1 demonstrator #5 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.439.0 — RAW PHB p.277: "Until the spell ends, one willing creature
you touch gains the ability to move up, down, and across vertical
surfaces and upside down along ceilings, while leaving its hands free.
The target also gains a climbing speed equal to its walking speed."
Action, V/S/M, Touch, Concentration, up to 1 hour.

The buff's ``effects.climb_speed_equals_walk`` flag IS the mechanic
— same shape as Speak with Animals' ``speaks_with_animals`` flag
(v2.438.0). The climb speed itself + "stick to walls" affordance stay
GM-narrated; the engine surfaces the flag on the buffs API so the
table can see it's active.

Caster: Thalindra Moonwhisper (Wizard) is the canonical caster in the
demo. Mira Greenleaf (Druid) is a fallback if Thalindra ever moves off
the spell list.

Tests:
  - Cast self-targets installs the buff with effects.climb_speed_equals_walk = true.
  - The installed buff carries duration_rounds=600 + concentration=true.
  - Krieger Stonefist (Barbarian) → 409 cannot_cast.
"""
from .conftest import CAMPAIGN_ID


async def _set_battle(gm_client, caster):
    """Stand up a tiny single-combatant battle so the buff has a hub
    state to install into."""
    pc_cb = {
        "id": f"tok_sc_caster_{caster['id']}",
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


async def _find_sc_caster(roster):
    """Find a roster character on the Druid/Sorcerer/Warlock/Wizard
    list. Demo Wizard (Thalindra) is the canonical choice; falls back
    through other casters if the seed shifts.
    """
    for name in (
        "Thalindra Moonwhisper",  # Wizard
        "Mira Greenleaf",         # Druid
    ):
        if name in roster:
            return roster[name]
    return None


async def test_cast_spider_climb_installs_buff(gm_client, roster):
    """A Wizard self-targets Spider Climb; the installed buff carries
    effects.climb_speed_equals_walk = true."""
    caster = await _find_sc_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Druid/Sorcerer/Warlock/Wizard in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spider_climb",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "spider-climb"
    assert body["buff_installed"] is True
    assert body["duration_rounds"] == 600
    assert body["target_character_id"] == caster["id"]

    buffs = await _get_caster_buffs(gm_client, caster["id"])
    sc_buff = next(
        (b for b in buffs if b.get("key") == "spider-climb"), None,
    )
    assert sc_buff is not None, f"spider-climb buff missing: {buffs}"
    effects = sc_buff.get("effects") or {}
    assert effects.get("climb_speed_equals_walk") is True


async def test_cast_spider_climb_buff_is_1_hour_concentration(gm_client, roster):
    """The installed buff carries duration_rounds=600 (1 hour) and
    concentration=true, matching RAW."""
    caster = await _find_sc_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Druid/Sorcerer/Warlock/Wizard in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spider_climb",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    buffs = await _get_caster_buffs(gm_client, caster["id"])
    sc_buff = next(
        (b for b in buffs if b.get("key") == "spider-climb"), None,
    )
    assert sc_buff is not None
    assert sc_buff.get("concentration") is True
    assert int(sc_buff.get("duration_rounds") or 0) == 600


async def test_cast_spider_climb_non_caster_rejected(gm_client, roster):
    """Krieger Stonefist is a Barbarian — not in Druid/Sorcerer/
    Warlock/Wizard. Returns 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, krieger)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spider_climb",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["error"] == "cannot_cast"
    assert "spider climb" in body["expected"].lower()
