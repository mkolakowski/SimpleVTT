"""Warding Bond — L2 abjuration, Cleric.
Phase 2 #28 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.493.0 — RAW PHB p.287: the warded target gains +1 AC, +1 to saving
throws, and resistance to all damage while within 60 ft of the caster
(who takes the same damage the target takes). 1 action, V/S/M, Touch,
1 hour, non-concentration.

Mechanized core rides two existing substrates: `ac_bonus` (read at
`_read_target_ac`) + `resistance_to: ["all"]` (read by
`_resistance_halve`). The +1 saving-throw bonus is GM-narrated (the
flat save-bonus read-site is equipped-item-only, not buff-aware); the
damage-share rider + 60-ft tether stay GM-narrated. The endpoint
mirrors the buff to the target's sheet so the sheet-based resistance
reader sees it.

Tests:
  - Cleric casts on an ally → buff installs with ac_bonus + resistance_to all.
  - Buff is 1-hour, non-concentration.
  - Targeting an ally installs on the ally, not the caster.
  - Non-caster (Barbarian) → 409.
  - Missing character_id → 400.
"""
from .conftest import CAMPAIGN_ID


async def _set_battle(gm_client, caster, ally=None):
    combatants = [{
        "id": f"tok_wb_caster_{caster['id']}",
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
            "id": f"tok_wb_ally_{ally['id']}",
            "char_id": ally["id"],
            "name": ally["name"],
            "initiative": 10,
            "hp_current": 75, "hp_max": 75,
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


def _find_cleric(roster):
    for name in ("Brother Tavik Stonebrow",):
        if name in roster:
            return roster[name]
    return None


async def test_cast_warding_bond_installs_ac_and_resistance(gm_client, roster):
    """A Cleric wards an ally; the installed buff carries ac_bonus == 1
    AND resistance_to including 'all' — both real read-sites."""
    caster = _find_cleric(roster)
    if caster is None:
        import pytest
        pytest.skip("no Cleric in the demo roster")
    ally = roster["Krieger Stonefist"]
    await _set_battle(gm_client, caster, ally=ally)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_warding_bond",
        json={"character_id": caster["id"],
              "target_character_id": ally["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "warding-bond"
    assert body["buff_installed"] is True
    assert body["duration_rounds"] == 600
    assert body["target_character_id"] == ally["id"]

    buffs = await _get_buffs(gm_client, ally["id"])
    wb = next((b for b in buffs if b.get("key") == "warding-bond"), None)
    assert wb is not None, f"warding-bond buff missing: {buffs}"
    effects = wb.get("effects") or {}
    assert int(effects.get("ac_bonus") or 0) == 1
    assert "all" in (effects.get("resistance_to") or [])


async def test_cast_warding_bond_is_1_hour_non_concentration(gm_client, roster):
    """The installed buff carries duration_rounds=600 (1 hour) and
    concentration=false, matching RAW."""
    caster = _find_cleric(roster)
    if caster is None:
        import pytest
        pytest.skip("no Cleric in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_warding_bond",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    buffs = await _get_buffs(gm_client, caster["id"])
    wb = next((b for b in buffs if b.get("key") == "warding-bond"), None)
    assert wb is not None
    assert wb.get("concentration") is False
    assert int(wb.get("duration_rounds") or 0) == 600


async def test_cast_warding_bond_on_ally_installs_on_ally(gm_client, roster):
    """Targeting an ally installs the buff on the ally, not the caster."""
    caster = _find_cleric(roster)
    if caster is None:
        import pytest
        pytest.skip("no Cleric in the demo roster")
    ally = roster["Krieger Stonefist"]
    await _set_battle(gm_client, caster, ally=ally)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_warding_bond",
        json={"character_id": caster["id"],
              "target_character_id": ally["id"]},
    )
    assert r.status_code == 200, r.text
    ally_buffs = await _get_buffs(gm_client, ally["id"])
    assert any(b.get("key") == "warding-bond" for b in ally_buffs), ally_buffs
    caster_buffs = await _get_buffs(gm_client, caster["id"])
    assert not any(b.get("key") == "warding-bond" for b in caster_buffs)


async def test_cast_warding_bond_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, krieger)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_warding_bond",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "cannot_cast"
    assert "warding bond" in r.json()["expected"].lower()


async def test_cast_warding_bond_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_warding_bond",
        json={},
    )
    assert r.status_code == 400, r.text
