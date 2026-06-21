"""Greater Invisibility — L4 illusion, Bard/Sorcerer/Wizard.
Phase 2 #32 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.499.0 — RAW PHB p.251: "You or a creature you touch becomes
invisible until the spell ends." Concentration up to 1 minute. Unlike
L2 Invisibility, it does NOT end when the target attacks or casts.

Rides the existing `effects.invisible` marker the attack-resolution
intercepts already read (`_attacker_has_invisible_advantage` → the
invisible attacker has advantage). The endpoint mirrors the buff to the
target sheet (the invisible reader is sheet-based, like the resistance
readers).

Tests:
  - Cast → buff installs with effects.invisible == True.
  - Buff is concentration=true, 1-minute (10 rounds), mirrored to sheet.
  - Targeting an ally installs on the ally, not the caster.
  - Non-caster (Barbarian) → 409.
  - Missing character_id → 400.
"""
from .conftest import CAMPAIGN_ID


async def _set_battle(gm_client, caster, ally=None):
    combatants = [{
        "id": f"tok_gi_caster_{caster['id']}",
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
            "id": f"tok_gi_ally_{ally['id']}",
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


def _find_gi_caster(roster):
    for name in (
        "Thalindra Moonwhisper",  # Wizard
        "Lyra Sunstrider",        # Bard
        "Zara Emberfire",         # Sorcerer
    ):
        if name in roster:
            return roster[name]
    return None


async def test_cast_gi_installs_invisible_marker(gm_client, roster):
    """Cast → buff carries effects.invisible == True."""
    caster = _find_gi_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Bard/Sorcerer/Wizard in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_greater_invisibility",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "greater-invisibility"
    assert body["buff_installed"] is True
    assert body["duration_rounds"] == 10

    buffs = await _get_buffs(gm_client, caster["id"])
    gi = next(
        (b for b in buffs if b.get("key") == "greater-invisibility"), None,
    )
    assert gi is not None, f"buff missing: {buffs}"
    assert (gi.get("effects") or {}).get("invisible") is True


async def test_cast_gi_is_concentration_and_mirrored(gm_client, roster):
    """The buff is concentration=true + 1-minute (10 rounds), and
    mirrored to the sheet `_buffs_active` (the invisible-reader
    precondition)."""
    caster = _find_gi_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Bard/Sorcerer/Wizard in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_greater_invisibility",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    buffs = await _get_buffs(gm_client, caster["id"])
    gi = next(
        (b for b in buffs if b.get("key") == "greater-invisibility"), None,
    )
    assert gi is not None
    assert gi.get("concentration") is True
    assert int(gi.get("duration_rounds") or 0) == 10

    sj = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caster['id']}/sheet-json",
    )
    assert sj.status_code == 200, sj.text
    active = (sj.json().get("sheet") or {}).get("_buffs_active") or []
    assert any(
        b.get("key") == "greater-invisibility" for b in active
    ), f"buff not mirrored to sheet _buffs_active: {active}"


async def test_cast_gi_on_ally_installs_on_ally(gm_client, roster):
    """Targeting an ally installs the buff on the ally, not the caster."""
    caster = _find_gi_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Bard/Sorcerer/Wizard in the demo roster")
    ally = roster["Krieger Stonefist"]
    await _set_battle(gm_client, caster, ally=ally)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_greater_invisibility",
        json={"character_id": caster["id"],
              "target_character_id": ally["id"]},
    )
    assert r.status_code == 200, r.text
    ally_buffs = await _get_buffs(gm_client, ally["id"])
    assert any(
        b.get("key") == "greater-invisibility" for b in ally_buffs
    ), ally_buffs
    caster_buffs = await _get_buffs(gm_client, caster["id"])
    assert not any(
        b.get("key") == "greater-invisibility" for b in caster_buffs
    )


async def test_cast_gi_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, krieger)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_greater_invisibility",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "cannot_cast"
    assert "greater invisibility" in r.json()["expected"].lower()


async def test_cast_gi_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_greater_invisibility",
        json={},
    )
    assert r.status_code == 400, r.text
