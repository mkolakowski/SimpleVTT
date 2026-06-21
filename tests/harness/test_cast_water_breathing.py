"""Water Breathing — L3 transmutation ritual, Druid/Ranger/Sorcerer/Wizard.
Phase 2 #49 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.525.0 — RAW PHB p.287: "This spell grants up to ten willing creatures
you can see within range the ability to breathe underwater until the
spell ends." 1 action, V/S/M, 30 ft, 24 hours, non-concentration.

Multi-target flag-buff sibling of Water Walk (#47): installs
`effects.water_breathing: True` on up to 10 chosen creatures (caster
auto-included), 24-hour duration (distinct from the 1-hour Potion of
Water Breathing buff that shares the slug). The flag IS the mechanic;
underwater breathing is GM-narrated.

Tests:
  - Self-cast installs the buff with water_breathing: true, 24h non-conc.
  - Multi-target fan-out: caster + a companion → 2 buffs installed.
  - Over-cap (>10 incl. caster) → 400.
  - Non-caster (Barbarian) → 409; missing character_id → 400.
"""
from .conftest import CAMPAIGN_ID


def _tok(char):
    return {
        "id": f"tok_wb_{char['id']}",
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
    for name in ("Mira Greenleaf", "Thalindra Moonwhisper", "Zara Emberfire"):
        if name in roster:
            return roster[name]
    return None


async def test_cast_wb_self_installs_buff(gm_client, roster):
    """Self-cast → buff carries effects.water_breathing == true, 24h
    non-concentration."""
    caster = _find_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no eligible caster in the demo roster")
    await _set_battle(gm_client, [_tok(caster)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_water_breathing",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "water-breathing"
    assert body["buffs_installed"] == 1
    assert body["duration_rounds"] == 14400

    buffs = await _get_buffs(gm_client, caster["id"])
    wb = next((b for b in buffs if b.get("key") == "water-breathing"), None)
    assert wb is not None, f"buff missing: {buffs}"
    assert (wb.get("effects") or {}).get("water_breathing") is True
    assert wb.get("concentration") is False
    assert int(wb.get("duration_rounds") or 0) == 14400


async def test_cast_wb_fans_out_to_companion(gm_client, roster):
    """Caster + a chosen companion → 2 buffs installed."""
    caster = _find_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no eligible caster in the demo roster")
    krieger = roster["Krieger Stonefist"]
    try:
        await _set_battle(gm_client, [_tok(caster), _tok(krieger)])
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_water_breathing",
            json={"character_id": caster["id"],
                  "target_character_ids": [krieger["id"]]},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["buffs_installed"] == 2, body
        assert set(body["targets"]) == {caster["id"], krieger["id"]}
        kb = await _get_buffs(gm_client, krieger["id"])
        assert any(b.get("key") == "water-breathing" for b in kb), kb
    finally:
        for cid in (caster["id"], krieger["id"]):
            await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/end_buff",
                json={"character_id": cid, "key": "water-breathing"},
            )


async def test_cast_wb_over_cap_400(gm_client, roster):
    """More than 10 unique targets (including the caster) → 400."""
    caster = _find_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no eligible caster in the demo roster")
    await _set_battle(gm_client, [_tok(caster)])
    bogus = list(range(910000, 910010))  # 10 + auto caster = 11 > 10
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_water_breathing",
        json={"character_id": caster["id"], "target_character_ids": bogus},
    )
    assert r.status_code == 400, r.text


async def test_cast_wb_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, [_tok(krieger)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_water_breathing",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "cannot_cast"
    assert "water breathing" in r.json()["expected"].lower()


async def test_cast_wb_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_water_breathing",
        json={},
    )
    assert r.status_code == 400, r.text
