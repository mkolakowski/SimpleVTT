"""Continual Flame — L2 evocation, Cleric/Wizard.
Phase 2 #55 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.537.0 — RAW PHB p.227: "A flame, equivalent in brightness to a torch,
springs forth from an object that you touch. ... it creates no heat and
doesn't use oxygen. A continual flame can be covered or hidden but not
smothered or quenched." 1 action, V/S/M, Touch, Until dispelled,
non-concentration.

Cast on an object (the engine models no objects/lighting), so this uses
the flexible-target shape (like Gentle Repose #54): a `continual-flame`
flag-buff on a tracked bearer, or a broadcast-only cast over a GM-named
object. The light + can't-be-smothered rider are GM-narrated.

Tests:
  - Cast on a tracked bearer → buff installs with continual_flame: true.
  - Cast with only target_name → broadcast-only, no buff.
  - Non-caster (Barbarian) → 409; missing character_id → 400.
"""
from .conftest import CAMPAIGN_ID


def _tok(char):
    return {
        "id": f"tok_cf_{char['id']}",
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


async def test_cast_cf_on_bearer_installs_buff(gm_client, roster):
    """Cast on a tracked bearer → buff carries continual_flame == true."""
    caster = _find_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Cleric/Wizard in the demo roster")
    bearer = roster["Krieger Stonefist"]
    try:
        await _set_battle(gm_client, [_tok(caster), _tok(bearer)])
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_continual_flame",
            json={"character_id": caster["id"],
                  "target_character_id": bearer["id"]},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["feature"] == "continual-flame"
        assert body["buff_installed"] is True
        assert body["target_character_id"] == bearer["id"]
        assert body["duration_rounds"] == 999999

        buffs = await _get_buffs(gm_client, bearer["id"])
        cf = next((b for b in buffs if b.get("key") == "continual-flame"), None)
        assert cf is not None, f"buff missing: {buffs}"
        assert (cf.get("effects") or {}).get("continual_flame") is True
        assert cf.get("concentration") is False
    finally:
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/end_buff",
            json={"character_id": bearer["id"], "key": "continual-flame"},
        )


async def test_cast_cf_no_target_is_broadcast_only(gm_client, roster):
    """Cast with only a free-text target_name → no buff installed."""
    caster = _find_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Cleric/Wizard in the demo roster")
    await _set_battle(gm_client, [_tok(caster)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_continual_flame",
        json={"character_id": caster["id"], "target_name": "the iron lantern"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["buff_installed"] is False
    assert body["target_character_id"] is None
    assert body["target_name"] == "the iron lantern"


async def test_cast_cf_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, [_tok(krieger)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_continual_flame",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "cannot_cast"
    assert "continual flame" in r.json()["expected"].lower()


async def test_cast_cf_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_continual_flame",
        json={},
    )
    assert r.status_code == 400, r.text
