"""Beacon of Hope — L3 abjuration, Cleric.
Phase 2 #40 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.507.0 — RAW PHB p.219: "each target has advantage on Wisdom saving
throws and death saving throws, and regains the maximum number of hit
points possible from any healing." Concentration, up to 1 minute.

Two of the three halves ride substrates: `save_advantage: ["WIS"]`
(`_buff_grants_save_advantage`) and `death_save_advantage: True` (the
new `_pc_has_death_save_advantage` read at `/death-save`, which rolls a
second d20 and keeps the higher). Max-healing is GM-narrated.

Tests:
  - Install → buff carries save_advantage[WIS] + death_save_advantage.
  - Death-save gate: a dying, beacon'd creature's /death-save reports
    `death_save_advantage: true`; a control (no beacon) reports false.
  - Non-caster (Barbarian) → 409; missing character_id → 400.
"""
from .conftest import CAMPAIGN_ID


def _tok(char):
    return {
        "id": f"tok_boh_{char['id']}",
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


async def _make_dying(gm_client, char_id):
    """Reset to alive, then drop to 0 HP so the death-save machine flips
    the character to ``dying``."""
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/death-save/override",
        json={"status": "alive", "successes": 0, "failures": 0},
    )
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"hp": {"current": 0}},
    )


async def _heal_to_full(gm_client, char_id):
    """Cleanup: revive + clear death-save state after a test."""
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/death-save/override",
        json={"status": "alive", "successes": 0, "failures": 0},
    )
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"hp": {"current": 20}},
    )


def _find_cleric(roster):
    for name in ("Brother Tavik Stonebrow",):
        if name in roster:
            return roster[name]
    return None


async def test_cast_beacon_installs_markers(gm_client, roster):
    """Cast → buff carries save_advantage[WIS] + death_save_advantage."""
    caster = _find_cleric(roster)
    if caster is None:
        import pytest
        pytest.skip("no Cleric in the demo roster")
    await _set_battle(gm_client, [_tok(caster)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_beacon_of_hope",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "beacon-of-hope"
    assert body["buff_installed"] is True
    assert body["duration_rounds"] == 10

    buffs = await _get_buffs(gm_client, caster["id"])
    boh = next((b for b in buffs if b.get("key") == "beacon-of-hope"), None)
    assert boh is not None, f"beacon-of-hope buff missing: {buffs}"
    eff = boh.get("effects") or {}
    sa = [str(x).upper()[:3] for x in (eff.get("save_advantage") or [])]
    assert "WIS" in sa, sa
    assert eff.get("death_save_advantage") is True
    assert boh.get("concentration") is True


async def test_beacon_grants_death_save_advantage(gm_client, roster):
    """A dying, beacon'd creature's /death-save reports advantage; a
    control with no beacon reports false."""
    caster = _find_cleric(roster)
    if caster is None:
        import pytest
        pytest.skip("no Cleric in the demo roster")
    tgt = roster["Krieger Stonefist"]
    try:
        await _set_battle(gm_client, [_tok(caster), _tok(tgt)])
        # Control first: dying, no beacon → advantage False.
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/end_buff",
            json={"character_id": tgt["id"], "key": "beacon-of-hope"},
        )
        await _make_dying(gm_client, tgt["id"])
        ctrl = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{tgt['id']}/death-save",
            json={},
        )
        assert ctrl.status_code == 200, ctrl.text
        assert ctrl.json().get("death_save_advantage") is False, ctrl.json()

        # Now beacon it + reset to dying, roll again → advantage True.
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_beacon_of_hope",
            json={"character_id": caster["id"],
                  "target_character_id": tgt["id"]},
        )
        assert r.status_code == 200, r.text
        await _make_dying(gm_client, tgt["id"])  # re-dying (control may have shifted state)
        warded = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{tgt['id']}/death-save",
            json={},
        )
        assert warded.status_code == 200, warded.text
        assert warded.json().get("death_save_advantage") is True, warded.json()
    finally:
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/end_buff",
            json={"character_id": tgt["id"], "key": "beacon-of-hope"},
        )
        await _heal_to_full(gm_client, tgt["id"])


async def test_cast_beacon_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, [_tok(krieger)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_beacon_of_hope",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "cannot_cast"
    assert "beacon of hope" in r.json()["expected"].lower()


async def test_cast_beacon_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_beacon_of_hope",
        json={},
    )
    assert r.status_code == 400, r.text
