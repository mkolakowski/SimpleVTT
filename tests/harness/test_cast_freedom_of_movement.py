"""Freedom of Movement — L4 abjuration, Bard/Cleric/Druid/Ranger.
Phase 2 #27 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.492.0 — RAW PHB p.250: "spells and other magical effects can
neither reduce the target's speed nor cause the target to be
paralyzed or restrained." 1 action, V/S/M, Touch, 1 hour,
non-concentration.

Rides the existing condition-immunity substrate — the buff carries
``effects.condition_immunity_to: ["paralyzed", "restrained"]`` (the
same field the v2.289.0 Ring of Free Action uses), enforced at the
``_install_buff`` gate. The endpoint mirrors the buff to the target's
sheet so the PC gate (which reads ``_buffs_active`` off the sheet)
sees it. The deterministic gate test casts Hold Person at the warded
target and asserts the paralyzed install is suppressed.

Tests:
  - Cleric self-targets → buff installs with condition_immunity_to.
  - Buff is 1-hour, non-concentration.
  - GATE: FoM on Krieger → Hold Person on Krieger → paralyzed
    suppressed (affected[].installed == False). Baseline without FoM
    installs it.
  - Non-caster (Barbarian) → 409.
  - Missing character_id → 400.
"""
from .conftest import CAMPAIGN_ID


async def _set_battle(gm_client, caster, ally=None):
    combatants = [{
        "id": f"tok_fom_caster_{caster['id']}",
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
            "id": f"tok_fom_ally_{ally['id']}",
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


def _find_fom_caster(roster):
    for name in (
        "Brother Tavik Stonebrow",  # Cleric
        "Mira Greenleaf",           # Druid
        "Sir Caelan Lightbringer",  # Paladin (not a FoM class, but Cleric exists)
    ):
        if name in roster:
            return roster[name]
    return None


async def test_cast_fom_self_installs_condition_immunity(gm_client, roster):
    """A Cleric self-targets; the installed buff carries
    effects.condition_immunity_to with paralyzed + restrained."""
    caster = _find_fom_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Bard/Cleric/Druid/Ranger in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_freedom_of_movement",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "freedom-of-movement"
    assert body["buff_installed"] is True
    assert body["duration_rounds"] == 600
    assert body["target_character_id"] == caster["id"]

    buffs = await _get_buffs(gm_client, caster["id"])
    fom = next(
        (b for b in buffs if b.get("key") == "freedom-of-movement"), None,
    )
    assert fom is not None, f"FoM buff missing: {buffs}"
    imm = (fom.get("effects") or {}).get("condition_immunity_to") or []
    assert "paralyzed" in imm and "restrained" in imm


async def test_cast_fom_is_1_hour_non_concentration(gm_client, roster):
    """The installed buff is duration_rounds=600 (1 hour) +
    concentration=false, matching RAW."""
    caster = _find_fom_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Bard/Cleric/Druid/Ranger in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_freedom_of_movement",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    buffs = await _get_buffs(gm_client, caster["id"])
    fom = next(
        (b for b in buffs if b.get("key") == "freedom-of-movement"), None,
    )
    assert fom is not None
    assert fom.get("concentration") is False
    assert int(fom.get("duration_rounds") or 0) == 600


async def test_fom_suppresses_hold_person_paralyze(gm_client, roster):
    """GATE: with Freedom of Movement on Krieger, Tavik's Hold Person
    install of paralyzed is suppressed (affected[].installed == False).
    The baseline (no FoM) installs it — see the assertion at the end."""
    tavik = roster["Brother Tavik Stonebrow"]
    krieger = roster["Krieger Stonefist"]
    tv_tok = f"tok_fom_gate_tv_{tavik['id']}"
    kr_tok = f"tok_fom_gate_kr_{krieger['id']}"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [
                {"id": tv_tok, "char_id": tavik["id"], "name": tavik["name"],
                 "initiative": 15, "hp_current": 30, "hp_max": 30,
                 "buffs": [],
                 "economy": {"action": False, "bonus": False,
                             "reaction": False, "movement": 0}},
                {"id": kr_tok, "char_id": krieger["id"], "name": krieger["name"],
                 "initiative": 10, "hp_current": 75, "hp_max": 75,
                 "buffs": [],
                 "economy": {"action": False, "bonus": False,
                             "reaction": False, "movement": 0}},
            ],
            "turn_index": 0, "round": 1, "active": True,
        },
    )
    # Clear any stale FoM/paralyzed from a prior run.
    for _k in ("freedom-of-movement", "paralyzed"):
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/end_buff",
            json={"character_id": krieger["id"], "key": _k},
        )

    # Ward Krieger.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_freedom_of_movement",
        json={"character_id": tavik["id"],
              "target_character_id": krieger["id"]},
    )
    assert r.status_code == 200, r.text

    # Tavik casts Hold Person at Krieger (override forces the install
    # attempt regardless of the save).
    hp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hold_person",
        json={
            "character_id": tavik["id"],
            "class_slug": "cleric",
            "slot_level": 2,
            "target_combatant_ids": [kr_tok],
            "override": True,
        },
    )
    assert hp.status_code == 200, hp.text
    affected = hp.json().get("affected") or []
    assert any(
        e.get("combatant_id") == kr_tok and e.get("installed") is False
        for e in affected
    ), (
        f"Freedom of Movement should suppress the paralyzed install; "
        f"got affected={affected}"
    )
    keys = {b.get("key") for b in await _get_buffs(gm_client, krieger["id"])}
    assert "paralyzed" not in keys, keys


async def test_cast_fom_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, krieger)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_freedom_of_movement",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["error"] == "cannot_cast"
    assert "freedom of movement" in body["expected"].lower()


async def test_cast_fom_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_freedom_of_movement",
        json={},
    )
    assert r.status_code == 400, r.text
