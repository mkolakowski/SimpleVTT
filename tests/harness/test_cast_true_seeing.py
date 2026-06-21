"""True Seeing — L6 divination, Bard/Cleric/Sorcerer/Warlock/Wizard.
Phase 2 #56 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.542.0 — RAW PHB p.284: "the creature has truesight, notices secret
doors hidden by magic, and can see into the Ethereal Plane, all out to a
range of 120 feet." Touch, 1 hour, non-concentration.

A two-substrate ride: the buff carries `sees_invisible: True` (the See
Invisibility #42/#43 attack-edge substrate — a True-Seeing creature
negates invisibility's attack edge for free) + `darkvision_ft: 120`
(the Darkvision #51 sense marker) + a `truesight` flag (illusions /
shapechangers / secret doors / Ethereal Plane GM-narrated).

Tests:
  - Self-cast installs the buff with sees_invisible + darkvision_ft 120 +
    truesight (1h, non-conc).
  - Touch an ally → the buff lands on the ally.
  - Mechanical: a True-Seeing attacker vs an invisible target → the
    invisible-target disadvantage is negated (control without True Seeing
    keeps the disadvantage).
  - Non-caster (Barbarian) → 409; missing character_id → 400.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _tok(char, tid=None, buffs=None, init=10):
    return {
        "id": tid or f"tok_ts_{char['id']}",
        "char_id": char["id"],
        "name": char["name"],
        "initiative": init,
        "hp_current": 40, "hp_max": 40,
        "buffs": buffs or [],
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
    for name in ("Thalindra Moonwhisper", "Brother Tavik Stonebrow"):
        if name in roster:
            return roster[name]
    return None


@pytest_asyncio.fixture(autouse=True)
async def _cleanup(gm_client, roster):
    yield
    for name in ("Pip Quickfingers", "Krieger Stonefist"):
        ch = roster.get(name)
        if not ch:
            continue
        for key in ("true-seeing", "invisible"):
            await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/end_buff",
                json={"character_id": ch["id"], "key": key},
            )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [], "turn_index": 0, "round": 1, "active": False},
    )


async def test_cast_ts_self_installs_two_substrate_markers(gm_client, roster):
    """Self-cast → buff carries sees_invisible + darkvision_ft 120 +
    truesight, 1h non-concentration."""
    caster = _find_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no eligible caster in the demo roster")
    await _set_battle(gm_client, [_tok(caster)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_true_seeing",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "true-seeing"
    assert body["truesight_ft"] == 120
    assert body["duration_rounds"] == 600
    assert body["target_character_id"] == caster["id"]

    buffs = await _get_buffs(gm_client, caster["id"])
    ts = next((b for b in buffs if b.get("key") == "true-seeing"), None)
    assert ts is not None, f"buff missing: {buffs}"
    eff = ts.get("effects") or {}
    assert eff.get("sees_invisible") is True
    assert int(eff.get("darkvision_ft") or 0) == 120
    assert eff.get("truesight") is True
    assert ts.get("concentration") is False


async def test_cast_ts_on_ally(gm_client, roster):
    """Touch an ally → the buff lands on the ally, not the caster."""
    caster = _find_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no eligible caster in the demo roster")
    ally = roster["Krieger Stonefist"]
    await _set_battle(gm_client, [_tok(caster), _tok(ally, "tok_ts_ally")])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_true_seeing",
        json={"character_id": caster["id"],
              "target_character_id": ally["id"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["target_character_id"] == ally["id"]
    ab = await _get_buffs(gm_client, ally["id"])
    assert any(b.get("key") == "true-seeing" for b in ab), ab


async def test_ts_attacker_negates_invisible_target_edge(gm_client, roster):
    """A True-Seeing attacker (Pip, granted by the caster) attacking an
    invisible target → the invisible-target disadvantage is negated; a
    control attacker without True Seeing keeps it."""
    caster = _find_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no eligible caster in the demo roster")
    pip = roster["Pip Quickfingers"]
    krieger = roster["Krieger Stonefist"]
    krieger_tok = "tok_ts_invtgt"
    await _set_battle(gm_client, [
        _tok(pip, "tok_ts_pip", init=20),
        _tok(krieger, krieger_tok,
             buffs=[{"key": "invisible", "name": "Invisible"}]),
    ])

    # Control: Pip (no True Seeing) attacks the invisible Krieger →
    # disadvantage_target_invisible.
    a = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={"character_id": pip["id"], "attack_index": 0,
              "target_combatant_id": krieger_tok, "override": True},
    )
    assert a.status_code == 200, a.text
    assert "target_invisible" in (a.json().get("roll_state_applied") or ""), (
        f"control should show target_invisible; got {a.json().get('roll_state_applied')!r}"
    )

    # Grant Pip True Seeing → the invisible-target disadvantage is negated.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_true_seeing",
        json={"character_id": caster["id"],
              "target_character_id": pip["id"]},
    )
    assert r.status_code == 200, r.text
    a2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={"character_id": pip["id"], "attack_index": 0,
              "target_combatant_id": krieger_tok, "override": True},
    )
    assert a2.status_code == 200, a2.text
    assert "target_invisible" not in (a2.json().get("roll_state_applied") or ""), (
        f"True Seeing should negate the invisible-target disadvantage; "
        f"got {a2.json().get('roll_state_applied')!r}"
    )


async def test_cast_ts_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, [_tok(krieger)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_true_seeing",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "cannot_cast"
    assert "true seeing" in r.json()["expected"].lower()


async def test_cast_ts_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_true_seeing",
        json={},
    )
    assert r.status_code == 400, r.text
