"""Phase B v2 — Flurry of Blows action-chip refund.

v2.49.117 — while ``flurry-of-blows-active`` is up on a Monk, the
next two UNARMED-STRIKE attacks don't burn the action chip; they
also decrement ``effects.unarmed_strikes_available``. When the
counter hits 0, the buff drops. Non-unarmed attacks (e.g.
Quarterstaff) DON'T refund — RAW Flurry grants unarmed strikes
only.

Tests:
  - Unarmed strike with Flurry active → action chip stays clear;
    buff counter ticks 2 → 1.
  - Second unarmed strike with Flurry active → buff counter ticks
    1 → 0; buff drops.
  - Non-unarmed attack with Flurry active → action chip marked
    normally; buff counter unchanged.
  - Unarmed strike WITHOUT Flurry → action chip marked normally
    (regression guard / control).
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


async def _seed_kael_and_bandit(gm_client, kael):
    """Two-combatant battle: Kael + a bandit punching bag."""
    templates = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/templates"
    )).json()
    bandit = next(t for t in templates if "bandit" in t["name"].lower())
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [
                {
                    "id": f"tok_chiprefund_{kael['id']}",
                    "char_id": kael["id"],
                    "name": kael["name"],
                    "initiative": 10,
                    "hp_current": 30, "hp_max": 30,
                    "buffs": [],
                    "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
                },
                {
                    "id": "tok_chiprefund_bandit",
                    "char_id": None,
                    "token_template_id": bandit["id"],
                    "name": "Punching Bag",
                    "initiative": 5,
                    "hp_current": 200, "hp_max": 200,
                    "buffs": [],
                    "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
                },
            ],
            "turn_index": 0, "round": 1, "active": True,
        },
    )


async def _kael_economy(gm_client, kael):
    """Read the current action/bonus chip state for Kael."""
    state_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{kael['id']}/economy"
    )
    return state_resp.json()


async def _kael_flurry_buff(gm_client, kael):
    """Return Kael's flurry-of-blows-active buff dict or None."""
    buffs_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{kael['id']}/buffs"
    )
    buffs = buffs_resp.json().get("buffs", [])
    for b in buffs:
        if (b or {}).get("key") == "flurry-of-blows-active":
            return b
    return None


async def test_unarmed_strike_with_flurry_active_refunds_chip(
    gm_client, gm_ws, kael_rested,
):
    """Activate Flurry → unarmed strike → action chip stays clear;
    buff counter 2 → 1."""
    kael = kael_rested
    await _seed_kael_and_bandit(gm_client, kael)
    # Activate Flurry.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_flurry_of_blows",
        json={"character_id": kael["id"]},
    )
    assert r.status_code == 200, r.text
    # Unarmed Strike is Kael's attack_index 0.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": kael["id"],
            "attack_index": 0,
            "target_combatant_id": "tok_chiprefund_bandit",
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    # Action chip should still be clear (refunded).
    econ = await _kael_economy(gm_client, kael)
    assert econ.get("action") is False, (
        f"action chip should be CLEAR after unarmed strike with Flurry "
        f"(refunded); got economy={econ}"
    )
    # Flurry buff counter ticks 2 → 1.
    buff = await _kael_flurry_buff(gm_client, kael)
    assert buff is not None, "Flurry buff should still be active (1 strike left)"
    assert buff.get("effects", {}).get("unarmed_strikes_available") == 1


async def test_second_unarmed_strike_consumes_flurry(
    gm_client, gm_ws, kael_rested,
):
    """Two unarmed strikes with Flurry → buff drops after the
    second one."""
    kael = kael_rested
    await _seed_kael_and_bandit(gm_client, kael)
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_flurry_of_blows",
        json={"character_id": kael["id"]},
    )
    # First unarmed strike.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": kael["id"],
            "attack_index": 0,
            "target_combatant_id": "tok_chiprefund_bandit",
            "override": True,
        },
    )
    # Second unarmed strike.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": kael["id"],
            "attack_index": 0,
            "target_combatant_id": "tok_chiprefund_bandit",
            "override": True,
        },
    )
    assert r.status_code == 200
    # Buff should be GONE — both strikes consumed.
    buff = await _kael_flurry_buff(gm_client, kael)
    assert buff is None, f"Flurry buff should be DROPPED after 2 strikes; got {buff}"


async def test_non_unarmed_attack_with_flurry_active_still_marks_chip(
    gm_client, gm_ws, kael_rested,
):
    """Quarterstaff (Martial Arts) attack while Flurry active should
    NOT refund the action chip + should NOT decrement the buff
    counter — RAW Flurry's free strikes are unarmed-only."""
    kael = kael_rested
    await _seed_kael_and_bandit(gm_client, kael)
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_flurry_of_blows",
        json={"character_id": kael["id"]},
    )
    # Quarterstaff is Kael's attack_index 1 ("Quarterstaff (Martial Arts)").
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": kael["id"],
            "attack_index": 1,
            "target_combatant_id": "tok_chiprefund_bandit",
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    # Action chip should be MARKED (normal weapon attack).
    econ = await _kael_economy(gm_client, kael)
    assert econ.get("action") is True, (
        f"Quarterstaff should mark action chip even with Flurry active; got {econ}"
    )
    # Buff counter unchanged.
    buff = await _kael_flurry_buff(gm_client, kael)
    assert buff is not None
    assert buff.get("effects", {}).get("unarmed_strikes_available") == 2


async def test_unarmed_strike_without_flurry_marks_chip(
    gm_client, gm_ws, kael_rested,
):
    """Control / regression guard: unarmed strike WITHOUT Flurry
    active should mark the action chip normally."""
    kael = kael_rested
    await _seed_kael_and_bandit(gm_client, kael)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": kael["id"],
            "attack_index": 0,
            "target_combatant_id": "tok_chiprefund_bandit",
            "override": True,
        },
    )
    assert r.status_code == 200
    econ = await _kael_economy(gm_client, kael)
    assert econ.get("action") is True, (
        f"unarmed strike without Flurry should mark chip; got {econ}"
    )
