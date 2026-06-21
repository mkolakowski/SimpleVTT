"""Enlarge/Reduce — L2 transmutation, Sorcerer/Wizard.
Phase 2 #26 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.491.0 — RAW PHB p.237: Enlarge grants advantage on STR checks and
STR saving throws; Reduce grants disadvantage. 1 action, V/S/M, 30 ft,
Concentration up to 1 minute.

Rides the existing STR-advantage / STR-disadvantage marker substrate —
the same read-sites the v2.192.0 Potion of Growth + v2.199.0 Potion of
Diminution use (`_pc_has_rage_str_save_advantage` reads
`effects.advantage_on` generically across all buffs). The size change +
the +/-1d4 weapon-damage rider stay GM-narrated. Unlike the potions,
the spell is concentration / 1 minute (10 rounds).

Tests:
  - Enlarge self → buff key "enlarge" with advantage_on str_check/str_save.
  - Reduce self → buff key "reduce" with disadvantage_on str_check/str_save.
  - Buff is concentration=true + duration_rounds=10.
  - Enlarge on an ally installs on the ally.
  - Non-caster (Barbarian) → 409.
  - Missing/invalid mode → 400; missing character_id → 400.
"""
from .conftest import CAMPAIGN_ID


async def _set_battle(gm_client, caster, ally=None):
    combatants = [{
        "id": f"tok_er_caster_{caster['id']}",
        "char_id": caster["id"],
        "name": caster["name"],
        "initiative": 15,
        "hp_current": 30, "hp_max": 30,
        "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }]
    if ally is not None:
        combatants.append({
            "id": f"tok_er_ally_{ally['id']}",
            "char_id": ally["id"],
            "name": ally["name"],
            "initiative": 10,
            "hp_current": 30, "hp_max": 30,
            "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0},
        })
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


def _find_er_caster(roster):
    for name in (
        "Thalindra Moonwhisper",  # Wizard
        "Zara Emberfire",         # Sorcerer
    ):
        if name in roster:
            return roster[name]
    return None


async def test_cast_enlarge_self_installs_str_advantage(gm_client, roster):
    """Enlarge self-targets → buff key 'enlarge' carries
    effects.advantage_on with str_check + str_save (the real roll
    read-site)."""
    caster = _find_er_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Sorcerer/Wizard in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_enlarge_reduce",
        json={"character_id": caster["id"], "mode": "enlarge"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "enlarge-reduce"
    assert body["mode"] == "enlarge"
    assert body["buff_installed"] is True
    assert body["duration_rounds"] == 10

    buffs = await _get_buffs(gm_client, caster["id"])
    b = next((x for x in buffs if x.get("key") == "enlarge"), None)
    assert b is not None, f"enlarge buff missing: {buffs}"
    adv = (b.get("effects") or {}).get("advantage_on") or []
    assert "str_check" in adv and "str_save" in adv


async def test_cast_reduce_self_installs_str_disadvantage(gm_client, roster):
    """Reduce self-targets → buff key 'reduce' carries
    effects.disadvantage_on with str_check + str_save."""
    caster = _find_er_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Sorcerer/Wizard in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_enlarge_reduce",
        json={"character_id": caster["id"], "mode": "reduce"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "reduce"
    buffs = await _get_buffs(gm_client, caster["id"])
    b = next((x for x in buffs if x.get("key") == "reduce"), None)
    assert b is not None, f"reduce buff missing: {buffs}"
    dis = (b.get("effects") or {}).get("disadvantage_on") or []
    assert "str_check" in dis and "str_save" in dis


async def test_cast_enlarge_is_concentration_1_minute(gm_client, roster):
    """The installed buff is concentration=true + duration_rounds=10
    (1 minute) — the spell, not the potion, semantics."""
    caster = _find_er_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Sorcerer/Wizard in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_enlarge_reduce",
        json={"character_id": caster["id"], "mode": "enlarge"},
    )
    assert r.status_code == 200, r.text
    buffs = await _get_buffs(gm_client, caster["id"])
    b = next((x for x in buffs if x.get("key") == "enlarge"), None)
    assert b is not None
    assert b.get("concentration") is True
    assert int(b.get("duration_rounds") or 0) == 10


async def test_cast_enlarge_on_ally_installs_on_ally(gm_client, roster):
    """Targeting an ally installs the buff on the ally, not the caster."""
    caster = _find_er_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Sorcerer/Wizard in the demo roster")
    ally = roster["Krieger Stonefist"]
    await _set_battle(gm_client, caster, ally=ally)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_enlarge_reduce",
        json={
            "character_id": caster["id"],
            "mode": "enlarge",
            "target_character_id": ally["id"],
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["target_character_id"] == ally["id"]
    ally_buffs = await _get_buffs(gm_client, ally["id"])
    assert any(b.get("key") == "enlarge" for b in ally_buffs), ally_buffs
    caster_buffs = await _get_buffs(gm_client, caster["id"])
    assert not any(b.get("key") == "enlarge" for b in caster_buffs)


async def test_cast_enlarge_reduce_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, krieger)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_enlarge_reduce",
        json={"character_id": krieger["id"], "mode": "enlarge"},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "cannot_cast"


async def test_cast_enlarge_reduce_bad_mode_400(gm_client, roster):
    """An invalid mode → 400."""
    caster = _find_er_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Sorcerer/Wizard in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_enlarge_reduce",
        json={"character_id": caster["id"], "mode": "embiggen"},
    )
    assert r.status_code == 400, r.text


async def test_cast_enlarge_reduce_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_enlarge_reduce",
        json={"mode": "enlarge"},
    )
    assert r.status_code == 400, r.text
