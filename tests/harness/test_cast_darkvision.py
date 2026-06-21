"""Darkvision — L2 transmutation, Druid/Ranger/Sorcerer/Wizard.
Phase 2 #51 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.533.0 — RAW PHB p.230: "You touch a willing creature to grant it the
ability to see in the dark. For the duration, that creature has
darkvision out to a range of 60 feet." 1 action, V/S/M, Touch, 8 hours,
non-concentration.

Single-target touch flag-buff carrying `effects.darkvision_ft: 60` — the
same descriptive darkvision marker the racial/Goggles-of-Night sense
substrate uses. Seeing in the dark is GM-narrated engine-wide; the marker
surfaces who has darkvision.

Tests:
  - Self-cast installs the buff with darkvision_ft: 60 (8h, non-conc).
  - Touch an ally → the buff lands on the ally.
  - Non-caster (Barbarian) → 409; missing character_id → 400.
"""
from .conftest import CAMPAIGN_ID


def _tok(char):
    return {
        "id": f"tok_dv_{char['id']}",
        "char_id": char["id"],
        "name": char["name"],
        "initiative": 10,
        "hp_current": 30, "hp_max": 30,
        "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _set_battle(gm_client, combatants):
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


def _find_caster(roster):
    for name in ("Thalindra Moonwhisper", "Mira Greenleaf", "Zara Emberfire"):
        if name in roster:
            return roster[name]
    return None


async def test_cast_dv_self_installs_buff(gm_client, roster):
    """Self-cast → buff carries effects.darkvision_ft == 60, 8h non-conc."""
    caster = _find_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no eligible caster in the demo roster")
    await _set_battle(gm_client, [_tok(caster)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_darkvision",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "darkvision"
    assert body["darkvision_ft"] == 60
    assert body["buff_installed"] is True
    assert body["duration_rounds"] == 4800
    assert body["target_character_id"] == caster["id"]

    buffs = await _get_buffs(gm_client, caster["id"])
    dv = next((b for b in buffs if b.get("key") == "darkvision"), None)
    assert dv is not None, f"buff missing: {buffs}"
    assert int((dv.get("effects") or {}).get("darkvision_ft") or 0) == 60
    assert dv.get("concentration") is False
    assert int(dv.get("duration_rounds") or 0) == 4800


async def test_cast_dv_on_ally(gm_client, roster):
    """Touch an ally → the buff lands on the ally, not the caster."""
    caster = _find_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no eligible caster in the demo roster")
    ally = roster["Krieger Stonefist"]
    try:
        await _set_battle(gm_client, [_tok(caster), _tok(ally)])
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_darkvision",
            json={"character_id": caster["id"],
                  "target_character_id": ally["id"]},
        )
        assert r.status_code == 200, r.text
        assert r.json()["target_character_id"] == ally["id"]
        ab = await _get_buffs(gm_client, ally["id"])
        assert any(b.get("key") == "darkvision" for b in ab), ab
        cb = await _get_buffs(gm_client, caster["id"])
        assert not any(b.get("key") == "darkvision" for b in cb)
    finally:
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/end_buff",
            json={"character_id": ally["id"], "key": "darkvision"},
        )


async def test_cast_dv_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, [_tok(krieger)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_darkvision",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "cannot_cast"
    assert "darkvision" in r.json()["expected"].lower()


async def test_cast_dv_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_darkvision",
        json={},
    )
    assert r.status_code == 400, r.text
