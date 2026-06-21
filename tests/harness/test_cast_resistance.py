"""Resistance — cantrip, Cleric/Druid.
Phase 2 #38 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.505.0 — RAW PHB p.272: "the target can roll a d4 and add the number
rolled to one saving throw of its choice ... The spell then ends."
1 action, V/S/M, Touch, Concentration up to 1 minute.

The save-side mirror of Guidance (#37). Installs a buff carrying
`effects.resistance_die: True` (keyed `resistance-cantrip` to stay
distinct from the damage `resistance-<type>` buffs), read at the
`/roll` save path (`_pc_has_resistance_cantrip`) — appends `+1d4` to a
manual save roll and CONSUMES the buff. Spell-prompted saves
(roll_request → /respond) are a filed follow-up.

Tests:
  - Cast → buff installs with effects.resistance_die == True.
  - Gate: a save /roll after Resistance appends +1d4 + fires the
    broadcast.
  - Consume: the buff is gone after one save; a second save has no +1d4.
  - A non-save /roll (a check) does NOT get the +1d4 (save-only).
  - Non-caster (Barbarian) → 409; missing character_id → 400.
"""
from .conftest import CAMPAIGN_ID


def _tok(char):
    return {
        "id": f"tok_rc_{char['id']}",
        "char_id": char["id"],
        "name": char["name"],
        "initiative": 10,
        "hp_current": 40, "hp_max": 40,
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


async def _roll(gm_client, char_id, stat_key):
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20+2",
            "stat_key": stat_key,
            "visibility": "public",
            "character_id": char_id,
            "note": stat_key,
        },
    )


def _find_caster(roster):
    for name in ("Brother Tavik Stonebrow", "Mira Greenleaf"):  # Cleric, Druid
        if name in roster:
            return roster[name]
    return None


async def test_cast_resistance_installs_marker(gm_client, roster):
    """Cast → buff carries effects.resistance_die == True."""
    caster = _find_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Cleric/Druid in the demo roster")
    await _set_battle(gm_client, [_tok(caster)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_resistance",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "resistance"
    assert body["buff_installed"] is True
    assert body["duration_rounds"] == 10

    buffs = await _get_buffs(gm_client, caster["id"])
    rc = next((b for b in buffs if b.get("key") == "resistance-cantrip"), None)
    assert rc is not None, f"resistance-cantrip buff missing: {buffs}"
    assert (rc.get("effects") or {}).get("resistance_die") is True
    assert rc.get("concentration") is True


async def test_resistance_adds_d4_to_save_then_consumes(gm_client, gm_ws, roster):
    """GATE + CONSUME: a save after Resistance appends +1d4 and fires the
    broadcast; the buff is then gone and a second save has no +1d4."""
    caster = _find_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Cleric/Druid in the demo roster")
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, [_tok(caster), _tok(krieger)])
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": krieger["id"], "key": "resistance-cantrip"},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_resistance",
        json={"character_id": caster["id"],
              "target_character_id": krieger["id"]},
    )
    assert r.status_code == 200, r.text

    gm_ws.mark()
    resp = await _roll(gm_client, krieger["id"], "dex_save")
    assert resp.status_code == 200, resp.text
    import asyncio as _asy
    await _asy.sleep(0.2)
    rolls = gm_ws.buffered("roll")
    assert rolls, "expected a roll broadcast"
    expr = (rolls[-1].get("data") or {}).get("expression") or ""
    assert "1d4" in expr, f"Resistance should append +1d4 to the save; got {expr!r}"

    fired = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "resistance-cantrip"
        and "+1d4" in str((m.get("data") or {}).get("feature_name", ""))
    ]
    assert fired, "expected a feature_used(source=resistance-cantrip, +1d4) broadcast"

    keys = {b.get("key") for b in await _get_buffs(gm_client, krieger["id"])}
    assert "resistance-cantrip" not in keys, f"should be consumed: {keys}"

    gm_ws.mark()
    resp2 = await _roll(gm_client, krieger["id"], "dex_save")
    assert resp2.status_code == 200, resp2.text
    await _asy.sleep(0.2)
    rolls2 = gm_ws.buffered("roll")
    assert rolls2, "expected a second roll broadcast"
    expr2 = (rolls2[-1].get("data") or {}).get("expression") or ""
    assert "1d4" not in expr2, f"consumed; second save should not add +1d4; got {expr2!r}"


async def test_resistance_does_not_add_to_a_check(gm_client, gm_ws, roster):
    """Resistance is save-only: an ability CHECK does not get the +1d4."""
    caster = _find_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Cleric/Druid in the demo roster")
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, [_tok(caster), _tok(krieger)])
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": krieger["id"], "key": "resistance-cantrip"},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_resistance",
        json={"character_id": caster["id"],
              "target_character_id": krieger["id"]},
    )
    assert r.status_code == 200, r.text
    gm_ws.mark()
    resp = await _roll(gm_client, krieger["id"], "dex_check")
    assert resp.status_code == 200, resp.text
    import asyncio as _asy
    await _asy.sleep(0.2)
    rolls = gm_ws.buffered("roll")
    assert rolls, "expected a roll broadcast"
    expr = (rolls[-1].get("data") or {}).get("expression") or ""
    assert "1d4" not in expr, (
        f"Resistance is save-only; a check should not get +1d4; got {expr!r}"
    )


async def test_cast_resistance_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, [_tok(krieger)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_resistance",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "cannot_cast"
    assert "resistance" in r.json()["expected"].lower()


async def test_cast_resistance_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_resistance",
        json={},
    )
    assert r.status_code == 400, r.text
