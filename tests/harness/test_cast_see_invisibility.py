"""See Invisibility — L2 divination, Bard/Sorcerer/Wizard.
Phase 2 #42 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.509.0 — RAW PHB p.274: "For the duration, you see invisible
creatures and objects as if they were visible, and you can see into the
Ethereal Plane. Ethereal creatures and objects appear ghostly and
translucent." 1 action, V/S/M, Self, 1 hour, non-concentration.

New ``_SPELL_BUFF_MAP["see-invisibility"]`` substrate carrying
``effects.sees_invisible: True`` — flag-buff shape (same as Detect Magic
v2.457.0 / Detect Evil and Good v2.456.0 / Tongues v2.445.0). The flag
IS the mechanic; detection + Ethereal-Plane sight are GM-narrated.

Tests:
  - Wizard self-cast installs the buff with sees_invisible: true.
  - Buff carries duration_rounds=600 (1 hour) + concentration=false.
  - Bard also succeeds (asserts the 3-class gate covers Bard).
  - Krieger (Barbarian) → 409 cannot_cast; missing character_id → 400.
"""
from .conftest import CAMPAIGN_ID


async def _set_battle(gm_client, caster):
    pc_cb = {
        "id": f"tok_si_caster_{caster['id']}",
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


async def _get_buffs(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    assert r.status_code == 200, r.text
    return r.json().get("buffs") or []


def _find_bard(roster):
    for name in ("Lyra Sunstrider",):
        if name in roster:
            return roster[name]
    return None


async def test_cast_si_wizard_installs_buff(gm_client, roster):
    """A Wizard self-casts See Invisibility; the installed buff carries
    effects.sees_invisible = true."""
    wiz = roster["Thalindra Moonwhisper"]
    await _set_battle(gm_client, wiz)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_see_invisibility",
        json={"character_id": wiz["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "see-invisibility"
    assert body["buff_installed"] is True
    assert body["duration_rounds"] == 600

    buffs = await _get_buffs(gm_client, wiz["id"])
    si_buff = next(
        (b for b in buffs if b.get("key") == "see-invisibility"), None,
    )
    assert si_buff is not None, f"see-invisibility buff missing: {buffs}"
    effects = si_buff.get("effects") or {}
    assert effects.get("sees_invisible") is True


async def test_cast_si_buff_is_1_hour_non_concentration(gm_client, roster):
    """The installed buff carries duration_rounds=600 (1 hour) and
    concentration=false, matching RAW."""
    wiz = roster["Thalindra Moonwhisper"]
    await _set_battle(gm_client, wiz)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_see_invisibility",
        json={"character_id": wiz["id"]},
    )
    assert r.status_code == 200, r.text
    buffs = await _get_buffs(gm_client, wiz["id"])
    si_buff = next(
        (b for b in buffs if b.get("key") == "see-invisibility"), None,
    )
    assert si_buff is not None
    assert si_buff.get("concentration") is False
    assert int(si_buff.get("duration_rounds") or 0) == 600


async def test_cast_si_bard_also_succeeds(gm_client, roster):
    """A Bard succeeds — asserts the bard/sorcerer/wizard gate covers
    Bard. Skips gracefully if the demo has no bard."""
    bard = _find_bard(roster)
    if bard is None:
        import pytest
        pytest.skip("no Bard in the demo roster")
    await _set_battle(gm_client, bard)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_see_invisibility",
        json={"character_id": bard["id"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["buff_installed"] is True


async def test_cast_si_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, krieger)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_see_invisibility",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "cannot_cast"
    assert "see invisibility" in r.json()["expected"].lower()


async def test_cast_si_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_see_invisibility",
        json={},
    )
    assert r.status_code == 400, r.text
