"""See Invisibility — attacker-advantage negation. Phase 2 #43 of
``docs/plans/cast-and-broadcast-tail.md``.

v2.510.0 — RAW PHB p.291: an invisible attacker has advantage *because
the target can't see it*. When the target carries `effects.sees_invisible`
(See Invisibility v2.509.0), that advantage no longer applies. New
`_target_sees_invisible` hub-read folded into the v2.152.0 invisible-
attacker advantage in the PC `/attack` (both bonused + bonusless
branches) and NPC `/npc_attack` pipelines.

Setup: Thalindra (Wizard) casts Greater Invisibility on Krieger (so
Krieger's sheet carries `effects.invisible`) and See Invisibility on
herself. Krieger then attacks two targets in the same battle:
  - Pip (no See Invisibility) → control: `advantage_invisible`.
  - Thalindra (See Invisibility) → the invisible advantage is negated.

Tests:
  - Control: an invisible attacker vs a normal target → advantage.
  - Negated: the same attacker vs a See-Invisibility target → the
    `invisible` advantage is gone.
"""
from .conftest import CAMPAIGN_ID


def _tok(char, tid, init=10, hp=60):
    return {
        "id": tid,
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


async def _setup(gm_client, roster):
    """Returns (thal, krieger, pip, thal_tok, pip_tok) with Krieger
    invisible and Thalindra seeing-invisible. Raises pytest.skip if the
    demo lacks the needed characters/spell."""
    import pytest
    thal = roster.get("Thalindra Moonwhisper")
    krieger = roster.get("Krieger Stonefist")
    pip = roster.get("Pip Quickfingers")
    if not (thal and krieger and pip):
        pytest.skip("demo roster missing Thalindra/Krieger/Pip")
    thal_tok = f"tok_si43_thal_{thal['id']}"
    krieger_tok = f"tok_si43_krg_{krieger['id']}"
    pip_tok = f"tok_si43_pip_{pip['id']}"
    await _set_battle(gm_client, [
        _tok(krieger, krieger_tok, init=25),
        _tok(thal, thal_tok, init=20),
        _tok(pip, pip_tok, init=10, hp=40),
    ])
    # Krieger becomes invisible (Thalindra casts Greater Invisibility on
    # the ally; mirrors effects.invisible to Krieger's sheet).
    gi = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_greater_invisibility",
        json={"character_id": thal["id"], "target_character_id": krieger["id"]},
    )
    assert gi.status_code == 200, gi.text
    # Thalindra casts See Invisibility on herself (non-concentration, so
    # it doesn't break the Greater Invisibility concentration).
    si = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_see_invisibility",
        json={"character_id": thal["id"]},
    )
    assert si.status_code == 200, si.text
    return thal, krieger, pip, thal_tok, pip_tok


async def _cleanup(gm_client, thal, krieger):
    for cid, key in (
        (krieger["id"], "greater-invisibility"),
        (thal["id"], "see-invisibility"),
    ):
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/end_buff",
            json={"character_id": cid, "key": key},
        )


async def test_invisible_attacker_has_advantage_vs_normal_target(
    gm_client, roster,
):
    """Control: an invisible attacker vs a target with no See
    Invisibility rolls with advantage (advantage_invisible)."""
    thal, krieger, pip, thal_tok, pip_tok = await _setup(gm_client, roster)
    try:
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
        assert "advantage" in state and "invisible" in state, (
            f"invisible attacker should have advantage vs a normal "
            f"target; got {state!r}"
        )
    finally:
        await _cleanup(gm_client, thal, krieger)


async def test_see_invisibility_negates_invisible_attacker_advantage(
    gm_client, roster,
):
    """An invisible attacker vs a See-Invisibility target loses the
    invisible advantage edge."""
    thal, krieger, pip, thal_tok, pip_tok = await _setup(gm_client, roster)
    try:
        a = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": krieger["id"],
                "attack_index": 0,
                "target_combatant_id": thal_tok,
                "override": True,
            },
        )
        assert a.status_code == 200, a.text
        state = a.json().get("roll_state_applied") or ""
        assert "invisible" not in state, (
            f"See Invisibility on the target should negate the invisible "
            f"attacker's advantage; got {state!r}"
        )
    finally:
        await _cleanup(gm_client, thal, krieger)
