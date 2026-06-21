"""Barkskin — L2 transmutation, Druid/Ranger.
Phase 2 #36 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.503.0 — RAW PHB p.217: "the target's AC can't be less than 16,
regardless of what kind of armor it is wearing." 1 action, V/S/M,
Touch, Concentration up to 1 hour.

Rides a new generic `effects.ac_floor` read in `_read_target_ac` —
the final AC is `max(total, 16)`, so a target already ≥16 is
unaffected and a lower-AC target is raised to 16. Hub-state read (no
sheet mirror). The gate test reads the deterministic `target_ac` the
`/attack` response surfaces (independent of the d20 roll).

Tests:
  - Cast → buff installs with effects.ac_floor == 16.
  - Buff is concentration=true, 1-hour.
  - GATE: a target PATCHed to AC 12 → after Barkskin, /attack target_ac
    is 16 (floored); a target already ≥16 is unchanged.
  - Non-caster (Barbarian) → 409.
  - Missing character_id → 400.
"""
from .conftest import CAMPAIGN_ID


def _tok(char, tag, hp=40):
    return {
        "id": f"tok_{tag}_{char['id']}",
        "char_id": char["id"],
        "name": char["name"],
        "initiative": 10,
        "hp_current": hp, "hp_max": hp,
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


async def _read_target_ac(gm_client, attacker, target_tok):
    a = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={"character_id": attacker["id"], "attack_index": 0,
              "target_combatant_id": target_tok, "override": True},
    )
    assert a.status_code == 200, a.text
    return a.json()["target_ac"]


def _find_bs_caster(roster):
    for name in ("Mira Greenleaf", "Rowan Quickbow"):  # Druid, Ranger
        if name in roster:
            return roster[name]
    return None


async def test_cast_barkskin_installs_ac_floor(gm_client, roster):
    """Cast → buff carries effects.ac_floor == 16."""
    caster = _find_bs_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Druid/Ranger in the demo roster")
    await _set_battle(gm_client, [_tok(caster, "bs")])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_barkskin",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "barkskin"
    assert body["buff_installed"] is True
    assert body["duration_rounds"] == 600

    buffs = await _get_buffs(gm_client, caster["id"])
    bs = next((b for b in buffs if b.get("key") == "barkskin"), None)
    assert bs is not None, f"barkskin buff missing: {buffs}"
    assert int((bs.get("effects") or {}).get("ac_floor") or 0) == 16
    assert bs.get("concentration") is True
    assert int(bs.get("duration_rounds") or 0) == 600


async def test_barkskin_floors_low_ac_to_16(gm_client, roster):
    """GATE: a naturally-low-AC target (Lyra, Bard AC 14) reads
    target_ac 16 after Barkskin. No PATCH — `ac` isn't a sheet-fields
    key, so we use a demo PC whose real AC is below the floor."""
    caster = _find_bs_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Druid/Ranger in the demo roster")
    tgt = roster["Lyra Sunstrider"]  # Bard, natural AC 14
    tgt_tok = f"tok_bs_{tgt['id']}"
    await _set_battle(gm_client, [_tok(caster, "bs"), _tok(tgt, "bs")])
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": tgt["id"], "key": "barkskin"},
    )
    try:
        base_ac = await _read_target_ac(gm_client, caster, tgt_tok)
        assert base_ac < 16, f"expected a sub-16 base AC to lift; got {base_ac}"
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_barkskin",
            json={"character_id": caster["id"],
                  "target_character_id": tgt["id"]},
        )
        assert r.status_code == 200, r.text
        floored = await _read_target_ac(gm_client, caster, tgt_tok)
        assert floored == 16, f"expected AC floored to 16, got {floored}"
    finally:
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/end_buff",
            json={"character_id": tgt["id"], "key": "barkskin"},
        )


async def test_barkskin_does_not_lower_high_ac(gm_client, roster):
    """A target already above the floor (Caelan, Paladin AC 18) is
    unaffected — proves the floor is a max(), not a set()."""
    caster = _find_bs_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Druid/Ranger in the demo roster")
    tgt = roster["Sir Caelan Lightbringer"]  # Paladin, natural AC 18
    tgt_tok = f"tok_bs_{tgt['id']}"
    await _set_battle(gm_client, [_tok(caster, "bs"), _tok(tgt, "bs")])
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": tgt["id"], "key": "barkskin"},
    )
    try:
        base_ac = await _read_target_ac(gm_client, caster, tgt_tok)
        assert base_ac > 16, f"expected a >16 base AC for this control; got {base_ac}"
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_barkskin",
            json={"character_id": caster["id"],
                  "target_character_id": tgt["id"]},
        )
        assert r.status_code == 200, r.text
        ac = await _read_target_ac(gm_client, caster, tgt_tok)
        assert ac == base_ac, (
            f"AC {base_ac} (>16) should be unaffected by the floor, got {ac}"
        )
    finally:
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/end_buff",
            json={"character_id": tgt["id"], "key": "barkskin"},
        )


async def test_cast_barkskin_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, [_tok(krieger, "bs")])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_barkskin",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "cannot_cast"
    assert "barkskin" in r.json()["expected"].lower()


async def test_cast_barkskin_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_barkskin",
        json={},
    )
    assert r.status_code == 400, r.text
