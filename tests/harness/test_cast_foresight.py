"""Foresight — L9 divination, Bard/Druid/Warlock/Wizard.
Phase 2 #35 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.502.0 — RAW PHB p.248: "advantage on attack rolls, ability checks,
and saving throws ... other creatures have disadvantage on attack
rolls against the target ... can't be surprised." 8 hours,
non-concentration.

The buff carries two hub-state markers (no sheet mirror):
``effects.foresight`` (read at the three advantage choke-points via
``_pc_has_foresight_advantage`` — attacks, checks, saves) and
``effects.attackers_have_disadvantage`` (the v2.500.0 Blur read-site).
All four gate tests below are deterministic on roll-state, so no dice
seeding is needed.

Tests:
  - Install → buff carries foresight + attackers_have_disadvantage.
  - Buff is 8-hour, non-concentration.
  - Check advantage (non-STR): /roll dex_check → 2d20kh1 (proves it's
    not STR-gated like Rage).
  - Save advantage (non-STR): Fireball DEX save vs the warded target →
    roll_request base_expression == "2d20kh1".
  - Attack advantage: the warded creature's attack → roll_state has
    "advantage".
  - Non-caster (Barbarian) → 409; missing character_id → 400.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _spell_index(gm_client, char_id, name):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    sheet = (r.json() or {}).get("sheet") or {}
    for i, sp in enumerate(sheet.get("spells") or []):
        nm = sp.get("name") if isinstance(sp, dict) else sp
        if str(nm).strip().lower() == name.strip().lower():
            return i
    return -1


def _tok(char, init=10, hp=60):
    return {
        "id": f"tok_fsgt_{char['id']}",
        "char_id": char["id"],
        "name": char["name"],
        "initiative": init,
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


@pytest_asyncio.fixture
async def thalindra(gm_client, roster):
    thal = roster["Thalindra Moonwhisper"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thal['id']}/rest",
        json={"type": "long"},
    )
    return thal


async def test_cast_foresight_installs_both_markers(gm_client, roster):
    """Cast → buff carries effects.foresight AND
    effects.attackers_have_disadvantage."""
    thal = roster["Thalindra Moonwhisper"]
    await _set_battle(gm_client, [_tok(thal)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_foresight",
        json={"character_id": thal["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "foresight"
    assert body["buff_installed"] is True
    assert body["duration_rounds"] == 4800

    buffs = await _get_buffs(gm_client, thal["id"])
    fs = next((b for b in buffs if b.get("key") == "foresight"), None)
    assert fs is not None, f"foresight buff missing: {buffs}"
    eff = fs.get("effects") or {}
    assert eff.get("foresight") is True
    assert eff.get("attackers_have_disadvantage") is True
    assert fs.get("concentration") is False
    assert int(fs.get("duration_rounds") or 0) == 4800


async def test_foresight_grants_advantage_on_non_str_check(gm_client, gm_ws, roster):
    """Foresight grants advantage on ALL ability checks — a DEX check
    swaps 1d20 → 2d20kh1 (Rage would NOT, since it's STR-only)."""
    krieger = roster["Krieger Stonefist"]
    thal = roster["Thalindra Moonwhisper"]
    await _set_battle(gm_client, [_tok(thal, init=20), _tok(krieger)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_foresight",
        json={"character_id": thal["id"],
              "target_character_id": krieger["id"]},
    )
    assert r.status_code == 200, r.text
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20+3",
            "stat_key": "dex_check",
            "visibility": "public",
            "character_id": krieger["id"],
            "note": "Acrobatics check",
        },
    )
    assert resp.status_code == 200, resp.text
    import asyncio as _asy
    await _asy.sleep(0.2)
    rolls = gm_ws.buffered("roll")
    assert rolls, "expected a roll broadcast"
    expr = (rolls[-1].get("data") or {}).get("expression") or ""
    assert "2d20kh1" in expr, (
        f"Foresight should swap 1d20 → 2d20kh1 on a DEX check; got {expr!r}"
    )


async def test_foresight_grants_advantage_on_non_str_save(
    gm_client, gm_ws, thalindra, roster,
):
    """Foresight grants advantage on ALL saves — a DEX save (Fireball)
    on the warded target rolls 2d20kh1 (Rage covers only STR saves)."""
    thal = thalindra
    krieger = roster["Krieger Stonefist"]
    fireball = await _spell_index(gm_client, thal["id"], "Fireball")
    if fireball < 0:
        import pytest
        pytest.skip("Thalindra must know Fireball")
    await _set_battle(gm_client, [_tok(thal, init=20), _tok(krieger)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_foresight",
        json={"character_id": thal["id"],
              "target_character_id": krieger["id"]},
    )
    assert r.status_code == 200, r.text
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thal["id"],
            "spell_index": fireball,
            "slot_level": 3,
            "class_slug": "wizard",
            "target_combatant_id": f"tok_fsgt_{krieger['id']}",
            "target_character_id": krieger["id"],
            "target_name": krieger["name"],
            "override": True,
            "override_range": True,
        },
    )
    assert resp.status_code == 200, resp.text
    import asyncio as _asy
    await _asy.sleep(0.2)
    rrs = gm_ws.buffered("roll_request")
    assert rrs, "expected a roll_request broadcast for Krieger's DEX save"
    assert (rrs[-1].get("data") or {}).get("base_expression") == "2d20kh1", (
        f"Foresight should grant advantage on the DEX save; "
        f"got {rrs[-1].get('data')}"
    )


async def test_foresight_grants_advantage_on_attack(gm_client, roster, bright_map):
    """The warded creature's attack roll gets advantage.

    ``bright_map`` neutralizes inherited ambient darkness so the roll-state
    reflects Foresight, not a can't-see cancellation (B16)."""
    krieger = roster["Krieger Stonefist"]
    thal = roster["Thalindra Moonwhisper"]
    pip = roster["Pip Quickfingers"]
    pip_tok = f"tok_fsgt_{pip['id']}"
    await _set_battle(gm_client, [
        _tok(krieger, init=20), _tok(thal, init=15),
        {"id": pip_tok, "char_id": pip["id"], "name": pip["name"],
         "initiative": 10, "hp_current": 40, "hp_max": 40, "buffs": [],
         "economy": {"action": False, "bonus": False,
                     "reaction": False, "movement": 0}},
    ])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_foresight",
        json={"character_id": thal["id"],
              "target_character_id": krieger["id"]},
    )
    assert r.status_code == 200, r.text
    a = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": krieger["id"],
            "attack_index": 0,
            "target_combatant_id": pip_tok,
            "override": True,
        },
    )
    assert a.status_code == 200, a.text
    state = a.json().get("roll_state_applied") or ""
    assert "advantage" in state and "disadvantage" not in state, (
        f"expected an advantage roll-state from Foresight; got {state!r}"
    )


async def test_cast_foresight_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, [_tok(krieger)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_foresight",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "cannot_cast"
    assert "foresight" in r.json()["expected"].lower()


async def test_cast_foresight_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_foresight",
        json={},
    )
    assert r.status_code == 400, r.text
