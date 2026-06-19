"""Jump — L1 transmutation, Druid/Ranger/Sorcerer/Wizard.
Phase 2 #10 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.453.0 — RAW PHB p.250: "You touch a creature. The creature's
jump distance is tripled until the spell ends." 1 action, V/S/M
(grasshopper's hind leg), Touch, 1 minute, non-concentration.

New ``_SPELL_BUFF_MAP["jump"]`` substrate carrying
``effects.jump_distance_tripled: True`` — flag-buff shape (same
as Tongues v2.445.0 / Comprehend Languages v2.450.0): the flag
IS the mechanic, the GM narrates the actual tripled distance.
Mirrors the v2.99.x Monk Step of the Wind precedent which uses
``jump_distance_doubled: True`` for its own jump rider.

Tests:
  - Cast self-targeted → buff installs with
    jump_distance_tripled: true.
  - Buff carries duration_rounds=10 + concentration=false.
  - Cast targeting an ally installs on the ally, not the caster.
  - Krieger (Barbarian) → 409 cannot_cast.
"""
from .conftest import CAMPAIGN_ID


async def _set_battle(gm_client, caster, ally=None):
    combatants = [{
        "id": f"tok_jump_caster_{caster['id']}",
        "char_id": caster["id"],
        "name": caster["name"],
        "initiative": 15,
        "hp_current": 30, "hp_max": 30,
        "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }]
    if ally is not None:
        combatants.append({
            "id": f"tok_jump_ally_{ally['id']}",
            "char_id": ally["id"],
            "name": ally["name"],
            "initiative": 10,
            "hp_current": 30, "hp_max": 30,
            "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0},
        })
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


async def _get_buffs(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    assert r.status_code == 200, r.text
    return r.json().get("buffs") or []


async def _find_jump_caster(roster):
    for name in (
        "Thalindra Moonwhisper",   # Wizard
    ):
        if name in roster:
            return roster[name]
    return None


async def test_cast_jump_self_installs_buff(gm_client, roster):
    """A Wizard self-targets Jump; the installed buff carries
    effects.jump_distance_tripled = true."""
    caster = await _find_jump_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Druid/Ranger/Sorcerer/Wizard in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_jump",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "jump"
    assert body["buff_installed"] is True
    assert body["duration_rounds"] == 10
    assert body["target_character_id"] == caster["id"]

    buffs = await _get_buffs(gm_client, caster["id"])
    jump_buff = next(
        (b for b in buffs if b.get("key") == "jump"), None,
    )
    assert jump_buff is not None, f"jump buff missing: {buffs}"
    effects = jump_buff.get("effects") or {}
    assert effects.get("jump_distance_tripled") is True


async def test_cast_jump_buff_is_1_minute_non_concentration(
    gm_client, roster,
):
    """The installed buff carries duration_rounds=10 (1 minute) and
    concentration=false, matching RAW."""
    caster = await _find_jump_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Druid/Ranger/Sorcerer/Wizard in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_jump",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    buffs = await _get_buffs(gm_client, caster["id"])
    jump_buff = next(
        (b for b in buffs if b.get("key") == "jump"), None,
    )
    assert jump_buff is not None
    assert jump_buff.get("concentration") is False
    assert int(jump_buff.get("duration_rounds") or 0) == 10


async def test_cast_jump_on_ally_installs_on_ally(gm_client, roster):
    """Targeting an ally installs the buff on the ally, not the
    caster (RAW: 'You touch a creature' — touch range)."""
    caster = await _find_jump_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Druid/Ranger/Sorcerer/Wizard in the demo roster")
    ally = roster["Krieger Stonefist"]
    await _set_battle(gm_client, caster, ally=ally)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_jump",
        json={
            "character_id": caster["id"],
            "target_character_id": ally["id"],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["target_character_id"] == ally["id"]
    assert body["buff_installed"] is True

    ally_buffs = await _get_buffs(gm_client, ally["id"])
    assert any(
        b.get("key") == "jump" for b in ally_buffs
    ), f"jump buff missing on ally: {ally_buffs}"

    caster_buffs = await _get_buffs(gm_client, caster["id"])
    assert not any(
        b.get("key") == "jump" for b in caster_buffs
    ), (
        f"caster shouldn't carry the buff when targeting an ally: "
        f"{caster_buffs}"
    )


async def test_cast_jump_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, krieger)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_jump",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["error"] == "cannot_cast"
    assert "jump" in body["expected"].lower()
