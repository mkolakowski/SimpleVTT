"""Protection from Poison — L2 abjuration, Cleric/Druid/Paladin/Ranger.
Phase 2 #25 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.490.0 — RAW PHB p.270: "For the duration, the target has
advantage on saving throws against being poisoned, and it has
resistance to poison damage." 1 action, V/S, Touch, 1 hour,
non-concentration.

Rides the existing ``_SPELL_BUFF_MAP["protection-from-poison"]``
substrate (``resistance_to: ["poison"]``, 600 rounds,
non-concentration) + the pre-existing ``_resistance_halve`` reader
the damage pipeline already calls — the same read-site the v2.186.0
Potion of Resistance uses. Same single-target-buff shape as
Longstrider (v2.452.0): one endpoint exposes a pre-wired substrate.

Tests:
  - Cleric self-targets → buff installs with resistance_to=["poison"].
  - Buff carries duration_rounds=600 + concentration=false.
  - Targeting an ally installs the buff on the ally, not the caster.
  - Krieger (Barbarian) → 409 cannot_cast.
  - Missing character_id → 400.
"""
from .conftest import CAMPAIGN_ID


async def _set_battle(gm_client, caster, ally=None):
    combatants = [{
        "id": f"tok_pfp_caster_{caster['id']}",
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
            "id": f"tok_pfp_ally_{ally['id']}",
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


def _find_pfp_caster(roster):
    for name in (
        "Brother Tavik Stonebrow",  # Cleric
        "Sir Caelan Lightbringer",  # Paladin
        "Mira Greenleaf",           # Druid
        "Rowan Quickbow",           # Ranger
    ):
        if name in roster:
            return roster[name]
    return None


async def test_cast_pfp_self_installs_poison_resistance(gm_client, roster):
    """A Cleric self-targets; the installed buff carries
    effects.resistance_to == ['poison'] — the real damage-pipeline
    read-site, not an inert flag."""
    caster = _find_pfp_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Cleric/Druid/Paladin/Ranger in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_protection_from_poison",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "protection-from-poison"
    assert body["buff_installed"] is True
    assert body["duration_rounds"] == 600
    assert body["target_character_id"] == caster["id"]

    buffs = await _get_buffs(gm_client, caster["id"])
    pfp = next(
        (b for b in buffs if b.get("key") == "protection-from-poison"),
        None,
    )
    assert pfp is not None, f"protection-from-poison buff missing: {buffs}"
    effects = pfp.get("effects") or {}
    assert "poison" in (effects.get("resistance_to") or [])


async def test_cast_pfp_buff_is_1_hour_non_concentration(gm_client, roster):
    """The installed buff carries duration_rounds=600 (1 hour) and
    concentration=false, matching RAW."""
    caster = _find_pfp_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Cleric/Druid/Paladin/Ranger in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_protection_from_poison",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    buffs = await _get_buffs(gm_client, caster["id"])
    pfp = next(
        (b for b in buffs if b.get("key") == "protection-from-poison"),
        None,
    )
    assert pfp is not None
    assert pfp.get("concentration") is False
    assert int(pfp.get("duration_rounds") or 0) == 600


async def test_cast_pfp_on_ally_installs_on_ally(gm_client, roster):
    """Targeting an ally installs the buff on the ally, not the caster
    (RAW: 'You touch a creature' — touch range)."""
    caster = _find_pfp_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Cleric/Druid/Paladin/Ranger in the demo roster")
    ally = roster["Krieger Stonefist"]
    await _set_battle(gm_client, caster, ally=ally)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_protection_from_poison",
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
        b.get("key") == "protection-from-poison" for b in ally_buffs
    ), f"buff missing on ally: {ally_buffs}"

    caster_buffs = await _get_buffs(gm_client, caster["id"])
    assert not any(
        b.get("key") == "protection-from-poison" for b in caster_buffs
    ), f"caster shouldn't carry the buff when targeting an ally: {caster_buffs}"


async def test_cast_pfp_mirrors_buff_to_sheet(gm_client, roster):
    """v2.496.1 — the resistance buff is mirrored to the target's sheet
    `_buffs_active`, so the sheet-based `_resistance_halve` reader (which
    the damage path consults off the DB sheet) actually sees it. Without
    the mirror the poison resistance installs but never halves damage."""
    caster = _find_pfp_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Cleric/Druid/Paladin/Ranger in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_protection_from_poison",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    sj = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caster['id']}/sheet-json",
    )
    assert sj.status_code == 200, sj.text
    active = (sj.json().get("sheet") or {}).get("_buffs_active") or []
    assert any(
        b.get("key") == "protection-from-poison" for b in active
    ), f"buff not mirrored to sheet _buffs_active: {active}"


async def test_cast_pfp_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, krieger)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_protection_from_poison",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["error"] == "cannot_cast"
    assert "protection from poison" in body["expected"].lower()


async def test_cast_pfp_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_protection_from_poison",
        json={},
    )
    assert r.status_code == 400, r.text
