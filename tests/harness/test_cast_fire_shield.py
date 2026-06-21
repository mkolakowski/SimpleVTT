"""Fire Shield — L4 evocation, Warlock/Wizard.
Phase 2 #46 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.522.0 — RAW PHB p.241: "The warm shield grants you resistance to cold
damage, and the chill shield grants you resistance to fire damage. ...
whenever a creature within 5 feet of you hits you with a melee attack,
the shield erupts ... the attacker takes 2d8 [fire/cold] damage."
1 action, V/S/M, Self, 10 minutes, non-concentration.

The self-only sibling of Protection from Energy (#30) — rides the same
`resistance_to` read-site (`_resistance_halve`), with the resisted type
chosen by the `shield` body param (warm → cold, chill → fire). Mirrors
the buff to the caster's sheet (per the v2.496.1 fix). The 2d8 reactive
damage + the bright-light radius are GM-narrated.

Tests:
  - shield=warm → buff carries resistance_to == [cold]; response resists==cold.
  - shield=chill → resistance_to == [fire].
  - Buff is non-concentration, 10-min (100 rounds), mirrored to the sheet.
  - Invalid/missing shield → 400.
  - Non-caster (Barbarian) → 409; missing character_id → 400.
"""
from .conftest import CAMPAIGN_ID


async def _set_battle(gm_client, caster):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [{
            "id": f"tok_fs_{caster['id']}",
            "char_id": caster["id"],
            "name": caster["name"],
            "initiative": 15,
            "hp_current": 30, "hp_max": 30,
            "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0},
        }], "turn_index": 0, "round": 1, "active": True},
    )


async def _get_buffs(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    assert r.status_code == 200, r.text
    return r.json().get("buffs") or []


def _find_caster(roster):
    for name in ("Thalindra Moonwhisper", "Zara Emberfire"):
        if name in roster:
            return roster[name]
    return None


async def test_cast_fs_warm_resists_cold(gm_client, roster):
    """shield=warm → buff carries resistance_to == [cold]."""
    caster = _find_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Warlock/Wizard in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_fire_shield",
        json={"character_id": caster["id"], "shield": "warm"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "fire-shield"
    assert body["shield"] == "warm"
    assert body["resists"] == "cold"
    assert body["duration_rounds"] == 100

    buffs = await _get_buffs(gm_client, caster["id"])
    fs = next((b for b in buffs if b.get("key") == "fire-shield"), None)
    assert fs is not None, f"buff missing: {buffs}"
    assert (fs.get("effects") or {}).get("resistance_to") == ["cold"]


async def test_cast_fs_chill_resists_fire(gm_client, roster):
    """shield=chill → buff carries resistance_to == [fire]."""
    caster = _find_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Warlock/Wizard in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_fire_shield",
        json={"character_id": caster["id"], "shield": "chill"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["resists"] == "fire"
    buffs = await _get_buffs(gm_client, caster["id"])
    fs = next((b for b in buffs if b.get("key") == "fire-shield"), None)
    assert fs is not None
    assert (fs.get("effects") or {}).get("resistance_to") == ["fire"]


async def test_cast_fs_non_concentration_and_mirrored(gm_client, roster):
    """The buff is non-concentration, 10-min (100 rounds), and mirrored
    to the sheet `_buffs_active` (the `_resistance_halve` precondition)."""
    caster = _find_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Warlock/Wizard in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_fire_shield",
        json={"character_id": caster["id"], "shield": "warm"},
    )
    assert r.status_code == 200, r.text
    buffs = await _get_buffs(gm_client, caster["id"])
    fs = next((b for b in buffs if b.get("key") == "fire-shield"), None)
    assert fs is not None
    assert fs.get("concentration") is False
    assert int(fs.get("duration_rounds") or 0) == 100

    sj = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caster['id']}/sheet-json",
    )
    assert sj.status_code == 200, sj.text
    active = (sj.json().get("sheet") or {}).get("_buffs_active") or []
    assert any(b.get("key") == "fire-shield" for b in active), (
        f"buff not mirrored to sheet _buffs_active: {active}"
    )


async def test_cast_fs_bad_shield_400(gm_client, roster):
    """An invalid shield (not warm/chill) → 400."""
    caster = _find_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Warlock/Wizard in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_fire_shield",
        json={"character_id": caster["id"], "shield": "frost"},
    )
    assert r.status_code == 400, r.text


async def test_cast_fs_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, krieger)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_fire_shield",
        json={"character_id": krieger["id"], "shield": "warm"},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "cannot_cast"
    assert "fire shield" in r.json()["expected"].lower()


async def test_cast_fs_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_fire_shield",
        json={"shield": "warm"},
    )
    assert r.status_code == 400, r.text
