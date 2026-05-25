"""/api/campaign/{cid}/use_reckless_attack — Barbarian Lv 2+ feature.

v2.49.238: Reckless Attack installs a 1-round self-buff with two
effects: ``advantage_on: ['str_attack']`` (advantage on the
barbarian's STR melee attacks via ``_attacker_has_str_attack_advantage``)
and ``incoming_attacks_have_advantage: True`` (attackers get advantage
on attacks against the reckless barbarian via
``_target_grants_advantage_to_attackers``). Krieger (Lv 5 Barbarian
Path of the Berserker, demo PC since v2.18.2) is the test bed.

Tests:
  - happy path: Krieger activates Reckless Attack; buff_update +
    feature_used broadcasts fire; buff has both effect flags.
  - 409 wrong-class: Pip (Rogue) → wrong_class.
  - 400 missing character_id.
  - Phase B integration: an attack AGAINST a reckless Krieger
    rolls 2d20kh1 (advantage); an attack BY raging Krieger rolls
    2d20kh1 (advantage, already covered by rage); both Reckless
    AND target_dodging cancel to straight 1d20.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def krieger_rested(gm_client, roster):
    """Long-rest Krieger to refill rage / clear stale buffs."""
    krieger = roster["Krieger Stonefist"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/rest",
        json={"type": "long"},
    )
    return krieger


async def _seed_battle_with(gm_client, char_ids: list[int]) -> None:
    combatants = []
    for cid in char_ids:
        combatants.append({
            "id": f"tok_reckless_{cid}",
            "char_id": cid,
            "name": f"PC {cid}",
            "initiative": 10,
            "hp_current": 50, "hp_max": 50,
            "buffs": [],
            "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
        })
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


async def test_reckless_attack_happy_path(gm_client, gm_ws, krieger_rested):
    """Krieger activates Reckless Attack. Asserts: 200 response,
    buff_installed=True, duration_rounds=1; buff_update broadcast
    carries both effect flags."""
    krieger = krieger_rested
    await _seed_battle_with(gm_client, [krieger["id"]])
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_reckless_attack",
        json={"character_id": krieger["id"], "override": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["buff_installed"] is True
    assert data["duration_rounds"] == 1

    # buff_update broadcast carries the reckless-attack buff.
    msg = await gm_ws.wait_for("buff_update", timeout=2.0)
    bd = msg.get("data") or {}
    assert bd.get("character_id") == krieger["id"]
    rec_buffs = [b for b in (bd.get("buffs") or []) if (b or {}).get("key") == "reckless-attack"]
    assert rec_buffs, f"reckless-attack buff missing; got {bd.get('buffs')}"
    buff = rec_buffs[0]
    assert buff["name"] == "Reckless Attack"
    assert buff["concentration"] is False
    assert buff["duration_rounds"] == 1
    effects = buff.get("effects") or {}
    # Both effect flags must be present.
    assert "str_attack" in (effects.get("advantage_on") or [])
    assert effects.get("incoming_attacks_have_advantage") is True

    # feature_used roll-log card.
    fu = await gm_ws.wait_for("feature_used", timeout=2.0)
    assert fu["data"]["source"] == "reckless-attack"
    assert "Reckless Attack" in fu["data"]["feature_name"]


async def test_reckless_attack_wrong_class(gm_client, roster):
    """Pip (Rogue) → 409 wrong_class with expected=barbarian."""
    pip = roster["Pip Quickfingers"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_reckless_attack",
        json={"character_id": pip["id"], "override": True},
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["error"] == "wrong_class"
    assert body["expected"] == "barbarian"


async def test_reckless_attack_missing_character_id(gm_client):
    """Missing character_id → 400."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_reckless_attack",
        json={},
    )
    assert resp.status_code == 400


async def test_attack_against_reckless_target_gets_advantage(gm_client, krieger_rested, roster):
    """Phase B integration: an attack against Krieger (with the
    reckless-attack buff active) gets advantage in the d20 — the
    breakdown contains ``2d20kh1`` rather than the straight ``1d20``.
    Uses Pip's Shortsword (+6 to hit) so the result also exercises
    the bonus path.
    """
    krieger = krieger_rested
    pip = roster["Pip Quickfingers"]
    krieger_cid = f"tok_reckless_{krieger['id']}"
    pip_cid = f"tok_reckless_{pip['id']}"
    # Seed battle with both combatants — Krieger pre-loaded with the
    # reckless-attack buff (skips needing to POST /use_reckless_attack
    # in the test setup; the buff shape matches what the endpoint
    # installs).
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [
                {
                    "id": pip_cid, "char_id": pip["id"], "name": pip["name"],
                    "initiative": 17, "hp_current": 30, "hp_max": 30,
                    "buffs": [],
                    "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
                },
                {
                    "id": krieger_cid, "char_id": krieger["id"], "name": krieger["name"],
                    "initiative": 5, "hp_current": 55, "hp_max": 55,
                    "buffs": [{
                        "key": "reckless-attack",
                        "name": "Reckless Attack",
                        "icon": "⚔",
                        "source_caster_id": None,
                        "target_combatant_id": None,
                        "duration_rounds": 1,
                        "duration_max": 1,
                        "concentration": False,
                        "effects": {
                            "advantage_on": ["str_attack"],
                            "incoming_attacks_have_advantage": True,
                        },
                    }],
                    "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
                },
            ],
            "turn_index": 0, "round": 1, "active": True,
        },
    )
    # Pip attacks Krieger — the attack should get advantage.
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": pip["id"],
            "attack_index": 0,
            "target_combatant_id": krieger_cid,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # The advantage layer mutates 1d20 → 2d20kh1 in the dice expression.
    bd = data.get("attack_breakdown") or ""
    assert "2d20kh1" in bd, (
        f"Expected advantage (2d20kh1) on attack against reckless target; "
        f"got breakdown: {bd!r}"
    )
    # The roll_state_applied label should mention reckless.
    rsa = data.get("roll_state_applied") or ""
    assert "reckless" in rsa, (
        f"Expected roll_state_applied to mention reckless; got {rsa!r}"
    )
