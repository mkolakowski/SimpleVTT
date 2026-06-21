"""Calm Emotions — L2 enchantment, Bard/Cleric/Warlock.
Phase 2 #53 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.535.0 — RAW PHB p.221: "Each humanoid in a 20-foot-radius sphere ...
must make a Charisma saving throw ... suppress any effect causing a
target to be charmed or frightened ... [or] make a target indifferent."
1 action, V/S, 60 ft, Concentration up to 1 minute.

The concentration sibling of Zone of Truth (#52) on the Sanctuary
DC-bake pattern: installs a `calm-emotions` buff on the caster carrying
`effects.calm_emotions: True` + the baked `save_dc` + `save_ability:
CHA`. The 20-ft sphere + per-humanoid saves + the GM's per-target effect
choice are GM-narrated.

Tests:
  - Cleric self-cast → buff carries calm_emotions + save_dc + CHA; the
    response surfaces the same DC (>= 8).
  - Buff is concentration, 1-min (10 rounds).
  - Non-caster (Barbarian) → 409; missing character_id → 400.
"""
from .conftest import CAMPAIGN_ID


def _tok(char):
    return {
        "id": f"tok_ce_{char['id']}",
        "char_id": char["id"],
        "name": char["name"],
        "initiative": 10,
        "hp_current": 30, "hp_max": 30,
        "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _set_battle(gm_client, caster):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [_tok(caster)], "turn_index": 0,
              "round": 1, "active": True},
    )


async def _get_buffs(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    assert r.status_code == 200, r.text
    return r.json().get("buffs") or []


def _find_caster(roster):
    for name in ("Brother Tavik Stonebrow", "Lyra Sunstrider"):
        if name in roster:
            return roster[name]
    return None


async def test_cast_ce_installs_dc_marker(gm_client, roster):
    """Cast → buff carries calm_emotions + save_dc + CHA; the response
    DC matches and is sane (>= 8)."""
    caster = _find_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Bard/Cleric in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_calm_emotions",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "calm-emotions"
    assert body["save_ability"] == "CHA"
    dc = int(body["save_dc"])
    assert dc >= 8, dc

    buffs = await _get_buffs(gm_client, caster["id"])
    ce = next((b for b in buffs if b.get("key") == "calm-emotions"), None)
    assert ce is not None, f"buff missing: {buffs}"
    eff = ce.get("effects") or {}
    assert eff.get("calm_emotions") is True
    assert int(eff.get("save_dc") or 0) == dc
    assert (eff.get("save_ability") or "").upper() == "CHA"


async def test_cast_ce_is_concentration_1_min(gm_client, roster):
    """The buff carries duration_rounds=10 (1 min) + concentration=true."""
    caster = _find_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Bard/Cleric in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_calm_emotions",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["duration_rounds"] == 10
    buffs = await _get_buffs(gm_client, caster["id"])
    ce = next((b for b in buffs if b.get("key") == "calm-emotions"), None)
    assert ce is not None
    assert ce.get("concentration") is True
    assert int(ce.get("duration_rounds") or 0) == 10


async def test_cast_ce_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, krieger)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_calm_emotions",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "cannot_cast"
    assert "calm emotions" in r.json()["expected"].lower()


async def test_cast_ce_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_calm_emotions",
        json={},
    )
    assert r.status_code == 400, r.text
