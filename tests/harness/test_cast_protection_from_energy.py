"""Protection from Energy — L3 abjuration, Cleric/Druid/Ranger/Sorc/Wiz.
Phase 2 #30 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.497.0 — RAW PHB p.270: "the willing creature you touch has
resistance to one damage type of your choice: acid, cold, fire,
lightning, or thunder." 1 action, V/S, Touch, Concentration up to
1 hour.

The sibling of Protection from Poison (#25) — rides the same
`resistance_to` read-site (`_resistance_halve`), with the type chosen
via the `damage_type` body param, and the spell is concentration. The
endpoint mirrors the buff to the target sheet (the resistance reader is
sheet-based, per the v2.496.1 fix).

Tests:
  - Cast with damage_type=fire → buff installs with resistance_to=[fire].
  - Buff is concentration=true, 1-hour, mirrored to the sheet.
  - Invalid/missing damage_type → 400.
  - Non-caster (Barbarian) → 409.
  - Missing character_id → 400.
"""
from .conftest import CAMPAIGN_ID


async def _set_battle(gm_client, caster, ally=None):
    combatants = [{
        "id": f"tok_pfe_caster_{caster['id']}",
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
            "id": f"tok_pfe_ally_{ally['id']}",
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


def _find_pfe_caster(roster):
    for name in (
        "Thalindra Moonwhisper",   # Wizard
        "Brother Tavik Stonebrow",  # Cleric
        "Mira Greenleaf",           # Druid
        "Zara Emberfire",           # Sorcerer
    ):
        if name in roster:
            return roster[name]
    return None


async def test_cast_pfe_installs_chosen_resistance(gm_client, roster):
    """Cast with damage_type=fire → buff carries resistance_to == [fire]."""
    caster = _find_pfe_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no eligible caster in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_protection_from_energy",
        json={"character_id": caster["id"], "damage_type": "fire"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "protection-from-energy"
    assert body["damage_type"] == "fire"
    assert body["buff_installed"] is True
    assert body["duration_rounds"] == 600

    buffs = await _get_buffs(gm_client, caster["id"])
    pfe = next(
        (b for b in buffs if b.get("key") == "protection-from-energy"), None,
    )
    assert pfe is not None, f"buff missing: {buffs}"
    assert (pfe.get("effects") or {}).get("resistance_to") == ["fire"]


async def test_cast_pfe_is_concentration_and_mirrored(gm_client, roster):
    """The buff is concentration=true, 1-hour, and mirrored to the sheet
    `_buffs_active` (the precondition `_resistance_halve` reads)."""
    caster = _find_pfe_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no eligible caster in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_protection_from_energy",
        json={"character_id": caster["id"], "damage_type": "cold"},
    )
    assert r.status_code == 200, r.text
    buffs = await _get_buffs(gm_client, caster["id"])
    pfe = next(
        (b for b in buffs if b.get("key") == "protection-from-energy"), None,
    )
    assert pfe is not None
    assert pfe.get("concentration") is True
    assert int(pfe.get("duration_rounds") or 0) == 600

    sj = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caster['id']}/sheet-json",
    )
    assert sj.status_code == 200, sj.text
    active = (sj.json().get("sheet") or {}).get("_buffs_active") or []
    assert any(
        b.get("key") == "protection-from-energy" for b in active
    ), f"buff not mirrored to sheet _buffs_active: {active}"


async def test_cast_pfe_bad_damage_type_400(gm_client, roster):
    """An invalid damage_type (e.g. necrotic, not one of the five) → 400."""
    caster = _find_pfe_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no eligible caster in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_protection_from_energy",
        json={"character_id": caster["id"], "damage_type": "necrotic"},
    )
    assert r.status_code == 400, r.text


async def test_cast_pfe_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, krieger)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_protection_from_energy",
        json={"character_id": krieger["id"], "damage_type": "fire"},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "cannot_cast"


async def test_cast_pfe_missing_character_id_400(gm_client):
    """Missing character_id → 400 (before the damage_type check matters)."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_protection_from_energy",
        json={"damage_type": "fire"},
    )
    assert r.status_code == 400, r.text
