"""Gentle Repose — L2 necromancy ritual, Cleric/Wizard.
Phase 2 #54 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.536.0 — RAW PHB p.245: "You touch a corpse or other remains. For the
duration, the target is protected from decay and can't become undead.
The spell also effectively extends the time limit on raising the target
from the dead ..." 1 action (ritual), V/S/M, Touch, 10 days,
non-concentration.

Flexible-target shape (like Identify #16): a tracked character's remains
get a `gentle-repose` flag-buff (`effects.gentle_repose: True`);
otherwise the cast is broadcast-only over a GM-narrated corpse. The
decay/undead/raise-window effects are GM-narrated.

Tests:
  - Cast on a tracked target → buff installs with gentle_repose: true.
  - Cast with no target (target_name only) → broadcast-only, no buff.
  - Non-caster (Barbarian) → 409; missing character_id → 400.
"""
from .conftest import CAMPAIGN_ID


def _tok(char):
    return {
        "id": f"tok_gr_{char['id']}",
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
    for name in ("Brother Tavik Stonebrow", "Thalindra Moonwhisper"):
        if name in roster:
            return roster[name]
    return None


async def test_cast_gr_on_target_installs_buff(gm_client, roster):
    """Cast on a tracked character's remains → buff carries
    effects.gentle_repose == true."""
    caster = _find_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Cleric/Wizard in the demo roster")
    remains = roster["Krieger Stonefist"]  # stand-in for the fallen ally
    try:
        await _set_battle(gm_client, [_tok(caster), _tok(remains)])
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_gentle_repose",
            json={"character_id": caster["id"],
                  "target_character_id": remains["id"]},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["feature"] == "gentle-repose"
        assert body["buff_installed"] is True
        assert body["target_character_id"] == remains["id"]
        assert body["duration_rounds"] == 144000

        buffs = await _get_buffs(gm_client, remains["id"])
        gr = next((b for b in buffs if b.get("key") == "gentle-repose"), None)
        assert gr is not None, f"buff missing: {buffs}"
        assert (gr.get("effects") or {}).get("gentle_repose") is True
        assert gr.get("concentration") is False
    finally:
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/end_buff",
            json={"character_id": remains["id"], "key": "gentle-repose"},
        )


async def test_cast_gr_no_target_is_broadcast_only(gm_client, roster):
    """Cast with only a free-text target_name → no buff installed (the
    corpse isn't a tracked entity)."""
    caster = _find_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Cleric/Wizard in the demo roster")
    await _set_battle(gm_client, [_tok(caster)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_gentle_repose",
        json={"character_id": caster["id"],
              "target_name": "the slain bandit"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["buff_installed"] is False
    assert body["target_character_id"] is None
    assert body["target_name"] == "the slain bandit"


async def test_cast_gr_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, [_tok(krieger)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_gentle_repose",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "cannot_cast"
    assert "gentle repose" in r.json()["expected"].lower()


async def test_cast_gr_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_gentle_repose",
        json={},
    )
    assert r.status_code == 400, r.text
