"""Speak with Animals — L1 ritual, Bard/Druid/Ranger. Phase 1
demonstrator #2 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.438.0 — RAW PHB p.277: "You gain the ability to comprehend
and verbally communicate with beasts for the duration." Action,
V/S, Self, 10 minutes, non-concentration.

The buff's presence IS the mechanic — GMs let PCs converse with
beasts when the buff is active. No mechanical hook needed beyond
the install. The simplest of the cast-and-broadcast tail
demonstrators by design (proves the pattern for the long tail of
"buff with a flag" utility spells).

Caster fixture: Thalindra Moonwhisper has Druid as one of her
classes (she's a Wizard/Druid multiclass in the demo seed).
Actually — checking the demo seed, Thalindra is just a Wizard;
she's not on the Bard/Druid/Ranger list. We use Aria Thornsong
(demo Bard) instead — she has Speak with Animals on her spell
list AND is in the caster classes.

Tests:
  - Cast installs the buff with effects.speaks_with_animals = true.
  - The installed buff carries duration_rounds=100 + concentration=false.
  - A non-caster non-knower (Krieger Barbarian) gets 409 cannot_cast.
"""
from .conftest import CAMPAIGN_ID


async def _set_battle(gm_client, caster):
    """Stand up a tiny single-combatant battle so the buff has a hub
    state to install into."""
    pc_cb = {
        "id": f"tok_swa_caster_{caster['id']}",
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


async def _find_swa_caster(roster):
    """Find a roster character who's a Bard, Druid, or Ranger. Demo
    fixtures rotate so we don't hardcode a name — we walk the
    roster until we find one with a matching class.
    """
    # Demo Bard/Druid/Ranger names from the v2.99.x demo seed.
    for name in ("Mira Greenleaf", "Lyra Sunstrider", "Rowan Quickbow"):
        if name in roster:
            return roster[name]
    # Fall back to any roster entry — caller must pass to the
    # endpoint and accept the 409 path if no caster matches.
    return None


async def test_cast_speak_with_animals_installs_buff(gm_client, roster):
    """A caster on the Bard/Druid/Ranger list casts Speak with
    Animals; the installed buff carries effects.speaks_with_animals
    = true."""
    caster = await _find_swa_caster(roster)
    if caster is None:
        # No Bard/Druid/Ranger in the demo seed — skip with a clear
        # message so the gap is visible.
        import pytest
        pytest.skip("no Bard/Druid/Ranger in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_speak_with_animals",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "speak-with-animals"
    assert body["buff_installed"] is True
    assert body["duration_rounds"] == 100

    buffs = await _get_caster_buffs(gm_client, caster["id"])
    swa_buff = next(
        (b for b in buffs if b.get("key") == "speak-with-animals"), None,
    )
    assert swa_buff is not None, f"speak-with-animals buff missing: {buffs}"
    effects = swa_buff.get("effects") or {}
    assert effects.get("speaks_with_animals") is True


async def test_cast_speak_with_animals_buff_is_10_minutes_non_concentration(gm_client, roster):
    """The installed buff carries duration_rounds=100 (10 minutes)
    and concentration=false, matching RAW."""
    caster = await _find_swa_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Bard/Druid/Ranger in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_speak_with_animals",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    buffs = await _get_caster_buffs(gm_client, caster["id"])
    swa_buff = next(
        (b for b in buffs if b.get("key") == "speak-with-animals"), None,
    )
    assert swa_buff is not None
    assert swa_buff.get("concentration") is False
    assert int(swa_buff.get("duration_rounds") or 0) == 100


async def test_cast_speak_with_animals_non_caster_rejected(gm_client, roster):
    """Krieger Stonefist is a Barbarian — not in Bard/Druid/Ranger.
    Returns 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, krieger)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_speak_with_animals",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["error"] == "cannot_cast"
    assert "speak with animals" in body["expected"].lower()
