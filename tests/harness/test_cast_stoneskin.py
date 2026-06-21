"""Stoneskin — L4 abjuration, Druid/Ranger/Sorcerer/Wizard.
Phase 2 #31 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.498.0 — RAW PHB p.278: "the target has resistance to nonmagical
bludgeoning, piercing, and slashing damage." 1 action, V/S/M, Touch,
Concentration up to 1 hour.

Rides the existing `nonmagical-<type>` resistance substrate
(`_resistance_halve` via `_resistance_matches_damage`, the same matcher
the Gaseous Form potion uses). The endpoint mirrors the buff to the
target sheet (the resistance reader is sheet-based, per v2.496.1).

Tests:
  - Cast → buff installs with the three nonmagical-* resistances.
  - Buff is concentration=true, 1-hour, mirrored to the sheet.
  - Targeting an ally installs on the ally, not the caster.
  - Non-caster (Barbarian) → 409.
  - Missing character_id → 400.
"""
from .conftest import CAMPAIGN_ID

_EXPECTED = {
    "nonmagical-bludgeoning",
    "nonmagical-piercing",
    "nonmagical-slashing",
}


async def _set_battle(gm_client, caster, ally=None):
    combatants = [{
        "id": f"tok_ss_caster_{caster['id']}",
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
            "id": f"tok_ss_ally_{ally['id']}",
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


def _find_ss_caster(roster):
    for name in (
        "Thalindra Moonwhisper",  # Wizard
        "Mira Greenleaf",         # Druid
        "Zara Emberfire",         # Sorcerer
        "Rowan Quickbow",         # Ranger
    ):
        if name in roster:
            return roster[name]
    return None


async def test_cast_stoneskin_installs_nonmagical_resistance(gm_client, roster):
    """Cast → buff carries resistance_to with the three nonmagical-*
    weapon-damage types."""
    caster = _find_ss_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Druid/Ranger/Sorcerer/Wizard in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_stoneskin",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "stoneskin"
    assert body["buff_installed"] is True
    assert body["duration_rounds"] == 600

    buffs = await _get_buffs(gm_client, caster["id"])
    ss = next((b for b in buffs if b.get("key") == "stoneskin"), None)
    assert ss is not None, f"stoneskin buff missing: {buffs}"
    resist = set((ss.get("effects") or {}).get("resistance_to") or [])
    assert _EXPECTED <= resist, f"missing nonmagical resistances: {resist}"


async def test_cast_stoneskin_is_concentration_and_mirrored(gm_client, roster):
    """The buff is concentration=true + 1-hour, and mirrored to the
    sheet `_buffs_active` (the resistance-reader precondition)."""
    caster = _find_ss_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Druid/Ranger/Sorcerer/Wizard in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_stoneskin",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    buffs = await _get_buffs(gm_client, caster["id"])
    ss = next((b for b in buffs if b.get("key") == "stoneskin"), None)
    assert ss is not None
    assert ss.get("concentration") is True
    assert int(ss.get("duration_rounds") or 0) == 600

    sj = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caster['id']}/sheet-json",
    )
    assert sj.status_code == 200, sj.text
    active = (sj.json().get("sheet") or {}).get("_buffs_active") or []
    assert any(
        b.get("key") == "stoneskin" for b in active
    ), f"buff not mirrored to sheet _buffs_active: {active}"


async def test_cast_stoneskin_on_ally_installs_on_ally(gm_client, roster):
    """Targeting an ally installs the buff on the ally, not the caster."""
    caster = _find_ss_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Druid/Ranger/Sorcerer/Wizard in the demo roster")
    ally = roster["Krieger Stonefist"]
    await _set_battle(gm_client, caster, ally=ally)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_stoneskin",
        json={"character_id": caster["id"],
              "target_character_id": ally["id"]},
    )
    assert r.status_code == 200, r.text
    ally_buffs = await _get_buffs(gm_client, ally["id"])
    assert any(b.get("key") == "stoneskin" for b in ally_buffs), ally_buffs
    caster_buffs = await _get_buffs(gm_client, caster["id"])
    assert not any(b.get("key") == "stoneskin" for b in caster_buffs)


async def test_cast_stoneskin_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, krieger)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_stoneskin",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "cannot_cast"
    assert "stoneskin" in r.json()["expected"].lower()


async def test_cast_stoneskin_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_stoneskin",
        json={},
    )
    assert r.status_code == 400, r.text
