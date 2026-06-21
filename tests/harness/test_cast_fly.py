"""Fly — L3 transmutation, Sorcerer/Warlock/Wizard.
Phase 2 #50 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.527.0 — RAW PHB p.243: "You touch a willing creature. The target
gains a flying speed of 60 feet for the duration. ... you can target one
additional creature for each slot level above 3rd." Touch, Concentration
up to 10 minutes, V/S/M.

Exposes the pre-wired `_SPELL_BUFF_MAP["fly"]` substrate (`effects.
fly_speed_ft: 60`, the same flight marker the Potion of Flying / Dragon
Wings ride) via a cast endpoint — the Longstrider/Mage Armor pattern.
Upcast adds one target per slot above 3rd.

Tests:
  - Self-cast installs the fly buff (fly_speed_ft=60, concentration, 100r).
  - Touch an ally → the buff lands on the ally.
  - Upcast (slot_level=5) lets 3 targets through; the cap echoes 3.
  - Over-cap at base (2 targets, slot 3) → 400 too_many_targets.
  - Non-caster (Barbarian) → 409; missing character_id → 400.
"""
from .conftest import CAMPAIGN_ID


def _tok(char):
    return {
        "id": f"tok_fly_{char['id']}",
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
    for name in ("Thalindra Moonwhisper", "Zara Emberfire"):
        if name in roster:
            return roster[name]
    return None


async def test_cast_fly_self_installs_buff(gm_client, roster):
    """Self-cast → buff carries effects.fly_speed_ft == 60, concentration,
    100 rounds."""
    caster = _find_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Sorcerer/Warlock/Wizard in the demo roster")
    await _set_battle(gm_client, [_tok(caster)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_fly",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "fly"
    assert body["buffs_installed"] == 1
    assert body["target_cap"] == 1
    assert body["duration_rounds"] == 100

    buffs = await _get_buffs(gm_client, caster["id"])
    fly = next((b for b in buffs if b.get("key") == "fly"), None)
    assert fly is not None, f"buff missing: {buffs}"
    assert int((fly.get("effects") or {}).get("fly_speed_ft") or 0) == 60
    assert fly.get("concentration") is True
    assert int(fly.get("duration_rounds") or 0) == 100


async def test_cast_fly_on_ally(gm_client, roster):
    """Touch an ally → the buff lands on the ally."""
    caster = _find_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Sorcerer/Warlock/Wizard in the demo roster")
    krieger = roster["Krieger Stonefist"]
    try:
        await _set_battle(gm_client, [_tok(caster), _tok(krieger)])
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_fly",
            json={"character_id": caster["id"],
                  "target_character_id": krieger["id"]},
        )
        assert r.status_code == 200, r.text
        assert r.json()["targets"] == [krieger["id"]]
        kb = await _get_buffs(gm_client, krieger["id"])
        assert any(b.get("key") == "fly" for b in kb), kb
    finally:
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/end_buff",
            json={"character_id": krieger["id"], "key": "fly"},
        )


async def test_cast_fly_upcast_allows_more_targets(gm_client, roster):
    """Upcast slot_level=5 → cap 3; casting on caster + 2 allies succeeds."""
    caster = _find_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Sorcerer/Warlock/Wizard in the demo roster")
    krieger = roster["Krieger Stonefist"]
    pip = roster["Pip Quickfingers"]
    try:
        await _set_battle(gm_client, [_tok(caster), _tok(krieger), _tok(pip)])
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_fly",
            json={"character_id": caster["id"], "slot_level": 5,
                  "target_character_ids": [caster["id"], krieger["id"], pip["id"]]},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["target_cap"] == 3
        assert body["buffs_installed"] == 3
    finally:
        for cid in (caster["id"], krieger["id"], pip["id"]):
            await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/end_buff",
                json={"character_id": cid, "key": "fly"},
            )


async def test_cast_fly_over_cap_at_base_400(gm_client, roster):
    """2 targets at base slot 3 (cap 1) → 400 too_many_targets."""
    caster = _find_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Sorcerer/Warlock/Wizard in the demo roster")
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, [_tok(caster), _tok(krieger)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_fly",
        json={"character_id": caster["id"],
              "target_character_ids": [caster["id"], krieger["id"]]},
    )
    assert r.status_code == 400, r.text
    assert r.json()["error"] == "too_many_targets"
    assert r.json()["limit"] == 1


async def test_cast_fly_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, [_tok(krieger)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_fly",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "cannot_cast"
    assert "fly" in r.json()["expected"].lower()


async def test_cast_fly_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_fly",
        json={},
    )
    assert r.status_code == 400, r.text
