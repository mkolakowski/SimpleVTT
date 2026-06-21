"""Guidance — cantrip, Cleric/Druid.
Phase 2 #37 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.504.0 — RAW PHB p.248: "the target can roll a d4 and add the number
rolled to one ability check of its choice ... The spell then ends."
1 action, V/S, Touch, Concentration up to 1 minute.

Installs a buff carrying `effects.guidance: True`, read at the `/roll`
ability-check path (`_pc_has_guidance`) — which appends `+1d4` to the
check expression and CONSUMES the buff (one check per cast, RAW).
Hub-state read, so it applies to in-combat checks; out-of-combat
exploration checks stay GM-narrated.

Tests:
  - Cast → buff installs with effects.guidance == True.
  - Gate: a check /roll after Guidance appends +1d4 to the expression
    + fires a feature_used(source=guidance) broadcast.
  - Consume: the buff is gone after one check; a second check has no +1d4.
  - Non-caster (Barbarian) → 409; missing character_id → 400.
"""
from .conftest import CAMPAIGN_ID


def _tok(char):
    return {
        "id": f"tok_gd_{char['id']}",
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


async def _roll_check(gm_client, char_id):
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20+3",
            "stat_key": "dex_check",
            "visibility": "public",
            "character_id": char_id,
            "note": "Acrobatics check",
        },
    )


def _find_guidance_caster(roster):
    for name in ("Brother Tavik Stonebrow", "Mira Greenleaf"):  # Cleric, Druid
        if name in roster:
            return roster[name]
    return None


async def test_cast_guidance_installs_marker(gm_client, roster):
    """Cast → buff carries effects.guidance == True."""
    caster = _find_guidance_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Cleric/Druid in the demo roster")
    await _set_battle(gm_client, [_tok(caster)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_guidance",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "guidance"
    assert body["buff_installed"] is True
    assert body["duration_rounds"] == 10

    buffs = await _get_buffs(gm_client, caster["id"])
    g = next((b for b in buffs if b.get("key") == "guidance"), None)
    assert g is not None, f"guidance buff missing: {buffs}"
    assert (g.get("effects") or {}).get("guidance") is True
    assert g.get("concentration") is True


async def test_guidance_adds_d4_to_check_then_consumes(gm_client, gm_ws, roster):
    """GATE + CONSUME: a check after Guidance appends +1d4 and fires the
    broadcast; the buff is then gone and a second check has no +1d4."""
    caster = _find_guidance_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Cleric/Druid in the demo roster")
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, [_tok(caster), _tok(krieger)])
    # Clear any stale guidance from a prior run.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": krieger["id"], "key": "guidance"},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_guidance",
        json={"character_id": caster["id"],
              "target_character_id": krieger["id"]},
    )
    assert r.status_code == 200, r.text

    gm_ws.mark()
    resp = await _roll_check(gm_client, krieger["id"])
    assert resp.status_code == 200, resp.text
    import asyncio as _asy
    await _asy.sleep(0.2)
    rolls = gm_ws.buffered("roll")
    assert rolls, "expected a roll broadcast"
    expr = (rolls[-1].get("data") or {}).get("expression") or ""
    assert "1d4" in expr, f"Guidance should append +1d4 to the check; got {expr!r}"

    # Broadcast fired.
    fired = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "guidance"
        and "+1d4" in str((m.get("data") or {}).get("feature_name", ""))
    ]
    assert fired, "expected a feature_used(source=guidance, +1d4) broadcast"

    # Consumed: buff gone.
    keys = {b.get("key") for b in await _get_buffs(gm_client, krieger["id"])}
    assert "guidance" not in keys, f"guidance should be consumed: {keys}"

    # A second check has no +1d4.
    gm_ws.mark()
    resp2 = await _roll_check(gm_client, krieger["id"])
    assert resp2.status_code == 200, resp2.text
    await _asy.sleep(0.2)
    rolls2 = gm_ws.buffered("roll")
    assert rolls2, "expected a second roll broadcast"
    expr2 = (rolls2[-1].get("data") or {}).get("expression") or ""
    assert "1d4" not in expr2, (
        f"Guidance was consumed; second check should not add +1d4; got {expr2!r}"
    )


async def test_cast_guidance_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, [_tok(krieger)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_guidance",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "cannot_cast"
    assert "guidance" in r.json()["expected"].lower()


async def test_cast_guidance_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_guidance",
        json={},
    )
    assert r.status_code == 400, r.text
