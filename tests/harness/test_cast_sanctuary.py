"""Sanctuary — L1 abjuration, Cleric.
Phase 2 #11 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.454.0 — RAW PHB p.272: "You ward a creature within range
against attack. Until the spell ends, any creature who targets
the warded creature with an attack or a harmful spell must first
make a Wisdom saving throw. On a failed save, the creature must
choose a new target or lose the attack or spell." 1 bonus action,
V/S/M (small silver mirror), 30 ft, 1 minute, non-concentration.

Rides the existing ``_SPELL_BUFF_MAP["sanctuary"]`` substrate
(``sanctuary_attacker_must_save: True`` +
``sanctuary_ends_on_offense: True``, 10 rounds, non-concentration)
plus the v2.97.52 install-time DC bake-in
(``8 + prof + spellcasting_mod``). The /use_attack Wis-save gate
already reads ``effects.dc`` back — zero new mechanical code.

Tests:
  - Cast self-targeted → buff installs with all three effect
    flags + a positive integer dc.
  - Buff carries duration_rounds=10 + concentration=false.
  - Cast targeting an ally installs the buff on the ally.
  - Wizard (non-cleric) → 409 cannot_cast.
  - Response and broadcast carry the dc; dc matches
    8 + prof + WIS-mod of the caster.
"""
from .conftest import CAMPAIGN_ID


async def _set_battle(gm_client, caster, ally=None):
    combatants = [{
        "id": f"tok_sanc_caster_{caster['id']}",
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
            "id": f"tok_sanc_ally_{ally['id']}",
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


async def _get_sheet(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert r.status_code == 200, r.text
    return (r.json() or {}).get("sheet") or {}


async def test_cast_sanctuary_self_installs_buff(gm_client, roster):
    """A Cleric self-wards Sanctuary; the installed buff carries
    sanctuary_attacker_must_save: true, sanctuary_ends_on_offense:
    true, and a positive integer dc."""
    cleric = roster["Brother Tavik Stonebrow"]
    await _set_battle(gm_client, cleric)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_sanctuary",
        json={"character_id": cleric["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "sanctuary"
    assert body["buff_installed"] is True
    assert body["duration_rounds"] == 10
    assert body["target_character_id"] == cleric["id"]
    assert isinstance(body["dc"], int) and body["dc"] >= 10

    buffs = await _get_buffs(gm_client, cleric["id"])
    sanc_buff = next(
        (b for b in buffs if b.get("key") == "sanctuary"), None,
    )
    assert sanc_buff is not None, f"sanctuary buff missing: {buffs}"
    effects = sanc_buff.get("effects") or {}
    assert effects.get("sanctuary_attacker_must_save") is True
    assert effects.get("sanctuary_ends_on_offense") is True
    assert effects.get("dc") == body["dc"]


async def test_cast_sanctuary_buff_is_1_minute_non_concentration(
    gm_client, roster,
):
    """The installed buff carries duration_rounds=10 (1 minute) and
    concentration=false, matching RAW."""
    cleric = roster["Brother Tavik Stonebrow"]
    await _set_battle(gm_client, cleric)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_sanctuary",
        json={"character_id": cleric["id"]},
    )
    assert r.status_code == 200, r.text
    buffs = await _get_buffs(gm_client, cleric["id"])
    sanc_buff = next(
        (b for b in buffs if b.get("key") == "sanctuary"), None,
    )
    assert sanc_buff is not None
    assert sanc_buff.get("concentration") is False
    assert int(sanc_buff.get("duration_rounds") or 0) == 10


async def test_cast_sanctuary_on_ally_installs_on_ally(gm_client, roster):
    """Targeting an ally wards the ally; caster doesn't carry the
    buff."""
    cleric = roster["Brother Tavik Stonebrow"]
    ally = roster["Krieger Stonefist"]
    await _set_battle(gm_client, cleric, ally=ally)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_sanctuary",
        json={
            "character_id": cleric["id"],
            "target_character_id": ally["id"],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["target_character_id"] == ally["id"]
    assert body["buff_installed"] is True

    ally_buffs = await _get_buffs(gm_client, ally["id"])
    assert any(
        b.get("key") == "sanctuary" for b in ally_buffs
    ), f"sanctuary buff missing on ally: {ally_buffs}"

    caster_buffs = await _get_buffs(gm_client, cleric["id"])
    assert not any(
        b.get("key") == "sanctuary" for b in caster_buffs
    ), (
        f"caster shouldn't carry the buff when targeting an ally: "
        f"{caster_buffs}"
    )


async def test_cast_sanctuary_non_cleric_rejected(gm_client, roster):
    """A Wizard (not Cleric per RAW) → 409 cannot_cast."""
    wiz = roster["Thalindra Moonwhisper"]
    await _set_battle(gm_client, wiz)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_sanctuary",
        json={"character_id": wiz["id"]},
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["error"] == "cannot_cast"
    assert "sanctuary" in body["expected"].lower()


async def test_cast_sanctuary_dc_matches_caster_profile(gm_client, roster):
    """DC = 8 + caster's proficiency_bonus + spellcasting modifier.
    For Tavik (Cleric 5, WIS 16, prof +3): 8 + 3 + 3 = 14."""
    cleric = roster["Brother Tavik Stonebrow"]
    await _set_battle(gm_client, cleric)
    sheet = await _get_sheet(gm_client, cleric["id"])
    prof = int(sheet.get("proficiency_bonus") or 2)
    wis_score = int((sheet.get("abilities") or {}).get("WIS") or 10)
    wis_mod = (wis_score - 10) // 2
    expected_dc = 8 + prof + wis_mod

    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_sanctuary",
        json={"character_id": cleric["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dc"] == expected_dc, (
        f"DC mismatch: response={body['dc']}, "
        f"expected=8+{prof}+{wis_mod}={expected_dc}"
    )
