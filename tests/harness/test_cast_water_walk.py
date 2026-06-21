"""Water Walk — L3 transmutation ritual, Cleric/Druid/Ranger/Sorcerer.
Phase 2 #47 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.523.0 — RAW PHB p.287: "This spell grants the ability to move across
any liquid surface ... as if it were harmless solid ground ... Up to ten
willing creatures you can see within range gain this ability." 1 action,
V/S/M, 30 ft, 1 hour, non-concentration.

Multi-target flag-buff (same fan-out as Feather Fall v2.444.0): installs
`effects.water_walk: True` on up to 10 chosen creatures (the caster is
auto-included). The flag IS the mechanic; surface-walking is GM-narrated.

Tests:
  - Self-cast installs the buff with water_walk: true, 1-hour non-conc.
  - Multi-target fan-out: caster + a companion → 2 buffs installed.
  - Over-cap (>10 incl. caster) → 400.
  - Non-caster (Barbarian) → 409; missing character_id → 400.
"""
from .conftest import CAMPAIGN_ID


def _tok(char):
    return {
        "id": f"tok_ww_{char['id']}",
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
    for name in ("Mira Greenleaf", "Brother Tavik Stonebrow", "Zara Emberfire"):
        if name in roster:
            return roster[name]
    return None


async def test_cast_ww_self_installs_buff(gm_client, roster):
    """Self-cast → buff carries effects.water_walk == true, 1-hour
    non-concentration."""
    caster = _find_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no eligible caster in the demo roster")
    await _set_battle(gm_client, [_tok(caster)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_water_walk",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "water-walk"
    assert body["buffs_installed"] == 1
    assert body["duration_rounds"] == 600

    buffs = await _get_buffs(gm_client, caster["id"])
    ww = next((b for b in buffs if b.get("key") == "water-walk"), None)
    assert ww is not None, f"buff missing: {buffs}"
    assert (ww.get("effects") or {}).get("water_walk") is True
    assert ww.get("concentration") is False
    assert int(ww.get("duration_rounds") or 0) == 600


async def test_cast_ww_fans_out_to_companion(gm_client, roster):
    """Caster + a chosen companion → 2 buffs installed."""
    caster = _find_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no eligible caster in the demo roster")
    krieger = roster["Krieger Stonefist"]
    try:
        await _set_battle(gm_client, [_tok(caster), _tok(krieger)])
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_water_walk",
            json={"character_id": caster["id"],
                  "target_character_ids": [krieger["id"]]},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["buffs_installed"] == 2, body
        assert set(body["targets"]) == {caster["id"], krieger["id"]}
        kb = await _get_buffs(gm_client, krieger["id"])
        assert any(b.get("key") == "water-walk" for b in kb), kb
    finally:
        for cid in (caster["id"], krieger["id"]):
            await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/end_buff",
                json={"character_id": cid, "key": "water-walk"},
            )


async def test_cast_ww_over_cap_400(gm_client, roster):
    """More than 10 unique targets (including the caster) → 400."""
    caster = _find_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no eligible caster in the demo roster")
    await _set_battle(gm_client, [_tok(caster)])
    # 10 distinct non-caster ids + the auto-included caster = 11 > 10.
    bogus = list(range(900000, 900010))
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_water_walk",
        json={"character_id": caster["id"], "target_character_ids": bogus},
    )
    assert r.status_code == 400, r.text


async def test_cast_ww_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, [_tok(krieger)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_water_walk",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "cannot_cast"
    assert "water walk" in r.json()["expected"].lower()


async def test_cast_ww_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_water_walk",
        json={},
    )
    assert r.status_code == 400, r.text
