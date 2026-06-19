"""Bless Water — L1 ritual, Cleric/Paladin. Phase 2 #6 of
``docs/plans/cast-and-broadcast-tail.md``.

v2.447.0 — RAW PHB p.219: "You touch one flask of water and cause it
to become holy water." Action, V/S/M (25 gp silver powder), Touch,
Instantaneous.

Installs a long-duration (24h) `holy-water-flask` flag buff on the
caster with `effects.holy_water_charges: 1`. The buff is a marker
that the caster now carries a flask of holy water; the GM/player
dismisses the buff when the flask is splashed. The 2d6 radiant
damage on undead/fiends per RAW stays GM-narrated.

Caster: Brother Tavik Stonebrow (Cleric) is the canonical caster;
Dame Seraphine Vael (Paladin) is the fallback.

Tests:
  - Cast installs the buff with holy_water_charges: 1.
  - Buff carries duration_rounds=14400 + concentration=false.
  - Krieger Stonefist (Barbarian) → 409 cannot_cast.
"""
from .conftest import CAMPAIGN_ID


async def _set_battle(gm_client, caster):
    pc_cb = {
        "id": f"tok_bw_caster_{caster['id']}",
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


async def _get_caster_buffs(gm_client, caster_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caster_id}/buffs",
    )
    assert r.status_code == 200, r.text
    return r.json().get("buffs") or []


async def _find_bw_caster(roster):
    for name in (
        "Brother Tavik Stonebrow",  # Cleric
        "Dame Seraphine Vael",      # Paladin
    ):
        if name in roster:
            return roster[name]
    return None


async def test_cast_bless_water_installs_buff(gm_client, roster):
    """A Cleric casts Bless Water; the installed buff carries
    effects.holy_water_charges = 1."""
    caster = await _find_bw_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Cleric/Paladin in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_bless_water",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "bless-water"
    assert body["buff_installed"] is True
    assert body["duration_rounds"] == 14400

    buffs = await _get_caster_buffs(gm_client, caster["id"])
    bw_buff = next(
        (b for b in buffs if b.get("key") == "holy-water-flask"), None,
    )
    assert bw_buff is not None, f"holy-water-flask buff missing: {buffs}"
    effects = bw_buff.get("effects") or {}
    assert effects.get("holy_water_charges") == 1


async def test_cast_bless_water_buff_is_24_hours_non_concentration(
    gm_client, roster,
):
    """The installed buff carries duration_rounds=14400 (24 hours)
    and concentration=false."""
    caster = await _find_bw_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Cleric/Paladin in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_bless_water",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    buffs = await _get_caster_buffs(gm_client, caster["id"])
    bw_buff = next(
        (b for b in buffs if b.get("key") == "holy-water-flask"), None,
    )
    assert bw_buff is not None
    assert bw_buff.get("concentration") is False
    assert int(bw_buff.get("duration_rounds") or 0) == 14400


async def test_cast_bless_water_non_caster_rejected(gm_client, roster):
    """Krieger Stonefist is a Barbarian — not in Cleric/Paladin.
    Returns 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, krieger)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_bless_water",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["error"] == "cannot_cast"
    assert "bless water" in body["expected"].lower()
