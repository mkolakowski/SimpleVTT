"""Mind Blank — L8 abjuration, Bard/Wizard.
Phase 2 #34 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.501.0 — RAW PHB p.259: the target is "immune to psychic damage,
any effect that would sense its emotions or read its thoughts,
divination spells, and the charmed condition." 24 hours,
non-concentration.

Mechanized core: the charmed-condition immunity rides the existing
`condition_immunity_to` substrate (the `_install_buff` gate via
`_target_condition_immune` — the SAME generic gate proven end-to-end in
`test_condition_immunity.py` for paralyzed/stunned/all). The buff is
mirrored to the target sheet so the gate (which reads `_buffs_active`)
sees it. Psychic-damage immunity + the divination/scry/wish clauses are
GM-narrated.

Tests:
  - Cast → buff installs with condition_immunity_to=["charmed"].
  - Buff is 24-hour, non-concentration, mirrored to the sheet
    `_buffs_active` (the gate precondition).
  - Targeting an ally installs on the ally, not the caster.
  - Non-caster (Barbarian) → 409.
  - Missing character_id → 400.
"""
from .conftest import CAMPAIGN_ID


async def _set_battle(gm_client, caster, ally=None):
    combatants = [{
        "id": f"tok_mb_caster_{caster['id']}",
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
            "id": f"tok_mb_ally_{ally['id']}",
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


def _find_mb_caster(roster):
    for name in (
        "Thalindra Moonwhisper",  # Wizard
        "Lyra Sunstrider",        # Bard
    ):
        if name in roster:
            return roster[name]
    return None


async def test_cast_mind_blank_installs_charmed_immunity(gm_client, roster):
    """Cast → buff carries effects.condition_immunity_to == ["charmed"]."""
    caster = _find_mb_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Bard/Wizard in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_mind_blank",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "mind-blank"
    assert body["buff_installed"] is True
    assert body["duration_rounds"] == 14400
    assert body["target_character_id"] == caster["id"]

    buffs = await _get_buffs(gm_client, caster["id"])
    mb = next((b for b in buffs if b.get("key") == "mind-blank"), None)
    assert mb is not None, f"mind-blank buff missing: {buffs}"
    assert "charmed" in ((mb.get("effects") or {}).get("condition_immunity_to") or [])


async def test_cast_mind_blank_is_24h_non_concentration_mirrored(
    gm_client, roster,
):
    """Buff is duration_rounds=14400 (24 h) + concentration=false, and
    mirrored to the sheet `_buffs_active` (the condition-immunity gate
    precondition)."""
    caster = _find_mb_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Bard/Wizard in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_mind_blank",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    buffs = await _get_buffs(gm_client, caster["id"])
    mb = next((b for b in buffs if b.get("key") == "mind-blank"), None)
    assert mb is not None
    assert mb.get("concentration") is False
    assert int(mb.get("duration_rounds") or 0) == 14400

    sj = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caster['id']}/sheet-json",
    )
    assert sj.status_code == 200, sj.text
    active = (sj.json().get("sheet") or {}).get("_buffs_active") or []
    assert any(
        b.get("key") == "mind-blank" for b in active
    ), f"buff not mirrored to sheet _buffs_active: {active}"


async def test_cast_mind_blank_on_ally_installs_on_ally(gm_client, roster):
    """Targeting an ally installs the buff on the ally, not the caster."""
    caster = _find_mb_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Bard/Wizard in the demo roster")
    ally = roster["Krieger Stonefist"]
    await _set_battle(gm_client, caster, ally=ally)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_mind_blank",
        json={"character_id": caster["id"],
              "target_character_id": ally["id"]},
    )
    assert r.status_code == 200, r.text
    ally_buffs = await _get_buffs(gm_client, ally["id"])
    assert any(b.get("key") == "mind-blank" for b in ally_buffs), ally_buffs
    caster_buffs = await _get_buffs(gm_client, caster["id"])
    assert not any(b.get("key") == "mind-blank" for b in caster_buffs)


async def test_cast_mind_blank_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, krieger)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_mind_blank",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "cannot_cast"
    assert "mind blank" in r.json()["expected"].lower()


async def test_cast_mind_blank_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_mind_blank",
        json={},
    )
    assert r.status_code == 400, r.text
