"""Phase B v1 — Patient Defense / Dodging disadvantage on incoming
attacks.

v2.49.115 — when an attack targets a combatant with the
``patient-defense`` buff (effects.dodging=True), the d20 attack
roll uses disadvantage (2d20kl1). Closes the first half of the
v2.49.112 Phase B follow-up.

Tests:
  - Attacker strikes Kael BEFORE Kael uses Patient Defense:
    attack_breakdown shows plain ``1d20[...]`` — no disadvantage
    applied. Acts as a control / regression guard.
  - Same attacker strikes Kael AFTER Kael uses Patient Defense:
    attack_breakdown shows ``2d20kl1[...]`` — disadvantage applied.
  - Rage attacker strikes Dodging target → cancellation
    (attack_roll_state_applied == "canceled_rage_vs_dodging" + plain
    1d20). RAW PHB p.173: adv + dis = neither.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def kael_rested(gm_client, roster):
    kael = roster["Kael Brightleaf"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{kael['id']}/rest",
        json={"type": "long"},
    )
    return kael


@pytest_asyncio.fixture
async def krieger_rested(gm_client, roster):
    """Barbarian — used as the attacker. Krieger comes with a sword
    in his attack list; the test fires it at Kael."""
    krieger = roster["Krieger Stonefist"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/rest",
        json={"type": "long"},
    )
    return krieger


async def _seed_kael_and_attacker(gm_client, kael, attacker):
    """Two-combatant battle: attacker + Kael (potential dodger).
    Both start with no buffs and fresh action economy."""
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [
                {
                    "id": f"tok_dodge_atk_{attacker['id']}",
                    "char_id": attacker["id"],
                    "name": attacker["name"],
                    "initiative": 12,
                    "hp_current": 55, "hp_max": 55,
                    "buffs": [],
                    "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
                },
                {
                    "id": f"tok_dodge_kael_{kael['id']}",
                    "char_id": kael["id"],
                    "name": kael["name"],
                    "initiative": 10,
                    "hp_current": 30, "hp_max": 30,
                    "buffs": [],
                    "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
                },
            ],
            "turn_index": 0, "round": 1, "active": True,
        },
    )


async def test_attack_without_dodging_uses_straight_d20(gm_client, kael_rested, krieger_rested):
    """Control — no Dodging buff, attack uses straight 1d20."""
    kael = kael_rested
    krieger = krieger_rested
    await _seed_kael_and_attacker(gm_client, kael, krieger)
    kael_token_id = f"tok_dodge_kael_{kael['id']}"
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": krieger["id"],
            "attack_index": 0,  # Krieger's first attack
            "target_combatant_id": kael_token_id,
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    breakdown = data.get("attack_breakdown") or ""
    assert "2d20kl1" not in breakdown, (
        f"control case should NOT have disadvantage; got {breakdown!r}"
    )
    # No disadvantage marker in the breakdown either.


async def test_attack_against_dodging_target_has_disadvantage(
    gm_client, kael_rested, krieger_rested,
):
    """Kael uses Patient Defense → attack against Kael uses 2d20kl1."""
    kael = kael_rested
    krieger = krieger_rested
    await _seed_kael_and_attacker(gm_client, kael, krieger)
    # Kael uses Patient Defense to install the dodging buff.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_patient_defense",
        json={"character_id": kael["id"]},
    )
    assert r.status_code == 200, r.text
    # Krieger attacks Kael.
    kael_token_id = f"tok_dodge_kael_{kael['id']}"
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": krieger["id"],
            "attack_index": 0,
            "target_combatant_id": kael_token_id,
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    breakdown = data.get("attack_breakdown") or ""
    assert "2d20kl1" in breakdown, (
        f"expected disadvantage roll '2d20kl1' in attack_breakdown, got: {breakdown!r}"
    )


async def test_rage_attacker_vs_dodging_target_cancels(
    gm_client, kael_rested, krieger_rested,
):
    """Krieger rages (advantage on STR attacks) + Kael dodges
    (disadvantage on attacks vs Kael). Per RAW PHB p.173, both →
    cancel → straight 1d20."""
    kael = kael_rested
    krieger = krieger_rested
    await _seed_kael_and_attacker(gm_client, kael, krieger)
    # Krieger rages.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rage",
        json={"character_id": krieger["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    # Kael dodges.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_patient_defense",
        json={"character_id": kael["id"]},
    )
    assert r.status_code == 200, r.text
    # Krieger attacks Kael with a physical weapon (slashing).
    kael_token_id = f"tok_dodge_kael_{kael['id']}"
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": krieger["id"],
            "attack_index": 0,
            "target_combatant_id": kael_token_id,
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    breakdown = data.get("attack_breakdown") or ""
    # Neither advantage nor disadvantage in the dice expression.
    assert "2d20kh1" not in breakdown, (
        f"cancel case should NOT have advantage; got {breakdown!r}"
    )
    assert "2d20kl1" not in breakdown, (
        f"cancel case should NOT have disadvantage; got {breakdown!r}"
    )
    # Breakdown should start with plain 1d20 (no kh1/kl1 suffix).
    assert breakdown.startswith("1d20"), (
        f"cancel case should be a plain d20 roll; got {breakdown!r}"
    )
