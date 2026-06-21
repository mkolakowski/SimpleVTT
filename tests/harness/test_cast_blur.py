"""Blur — L2 illusion, Sorcerer/Wizard.
Phase 2 #33 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.500.0 — RAW PHB p.219: "any creature has disadvantage on attack
rolls against you." 1 action, V, Self, Concentration up to 1 minute.

Needed a NEW generic read-site: `_target_blur_imposes_disadvantage`
reads the target combatant's hub buffs for
`effects.attackers_have_disadvantage` and the /attack + /npc_attack
flows fold it into the same disadvantage cancel logic as Dodge. No
sheet mirror needed (hub-state read, like Dodge / Reckless Attack).

Tests:
  - Cast → self buff installs with attackers_have_disadvantage=True.
  - Buff is concentration=true, 1-minute (10 rounds).
  - GATE: an attacker hitting the blurred target rolls at disadvantage
    (`roll_state_applied == "disadvantage_blur"`).
  - Non-caster (Barbarian) → 409.
  - Missing character_id → 400.
"""
from .conftest import CAMPAIGN_ID


def _tok(char, tag, init=10, hp=30):
    return {
        "id": f"tok_{tag}_{char['id']}",
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


def _find_blur_caster(roster):
    for name in (
        "Thalindra Moonwhisper",  # Wizard
        "Zara Emberfire",         # Sorcerer
    ):
        if name in roster:
            return roster[name]
    return None


async def test_cast_blur_installs_attacker_disadvantage(gm_client, roster):
    """Cast → self buff carries effects.attackers_have_disadvantage."""
    caster = _find_blur_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Sorcerer/Wizard in the demo roster")
    await _set_battle(gm_client, [_tok(caster, "blur")])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_blur",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "blur"
    assert body["buff_installed"] is True
    assert body["duration_rounds"] == 10
    assert body["target_character_id"] == caster["id"]

    buffs = await _get_buffs(gm_client, caster["id"])
    blur = next((b for b in buffs if b.get("key") == "blur"), None)
    assert blur is not None, f"blur buff missing: {buffs}"
    assert (blur.get("effects") or {}).get("attackers_have_disadvantage") is True


async def test_cast_blur_is_concentration_1_minute(gm_client, roster):
    """The buff is concentration=true + 1-minute (10 rounds)."""
    caster = _find_blur_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Sorcerer/Wizard in the demo roster")
    await _set_battle(gm_client, [_tok(caster, "blur")])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_blur",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    buffs = await _get_buffs(gm_client, caster["id"])
    blur = next((b for b in buffs if b.get("key") == "blur"), None)
    assert blur is not None
    assert blur.get("concentration") is True
    assert int(blur.get("duration_rounds") or 0) == 10


async def test_blur_imposes_disadvantage_on_attacker(gm_client, roster):
    """GATE: with Blur on the target, an attacker's d20 attack roll gets
    disadvantage (`roll_state_applied == "disadvantage_blur"`)."""
    pip = roster["Pip Quickfingers"]
    target = _find_blur_caster(roster)
    if target is None:
        import pytest
        pytest.skip("no Sorcerer/Wizard in the demo roster")
    target_tok = f"tok_blurtgt_{target['id']}"
    await _set_battle(gm_client, [
        _tok(pip, "bluratk", init=20, hp=40),
        {
            "id": target_tok, "char_id": target["id"], "name": target["name"],
            "initiative": 10, "hp_current": 60, "hp_max": 60, "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0},
        },
    ])
    # Target blurs itself.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_blur",
        json={"character_id": target["id"]},
    )
    assert r.status_code == 200, r.text

    a = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": pip["id"],
            "attack_index": 0,
            "target_combatant_id": target_tok,
            "override": True,
        },
    )
    assert a.status_code == 200, a.text
    assert a.json().get("roll_state_applied") == "disadvantage_blur", a.json()


async def test_cast_blur_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, [_tok(krieger, "blur")])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_blur",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "cannot_cast"
    assert "blur" in r.json()["expected"].lower()


async def test_cast_blur_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_blur",
        json={},
    )
    assert r.status_code == 400, r.text
