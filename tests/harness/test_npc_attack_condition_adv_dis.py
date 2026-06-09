"""Phase 2c — NPC-attacker condition automation on /npc_attack.

Phase 2a (v2.152.0) covered PC `/attack`'s attacker- and target-side
condition adv/dis source set; Phase 2b (v2.153.0) extended condition
disadvantage to PC `/api/campaign/{id}/roll` for saves + checks. The
NPC-attack path was the last gap: NPC attackers carrying Poisoned
or Invisible weren't reading their own combatant.buffs, and an NPC
attacking a Blinded/Restrained PC didn't gain advantage either.

Phase 2c (v2.154.0) wires three sources into /npc_attack:
  - NPC attacker condition disadvantage (Blinded / Poisoned /
    Restrained / Frightened / Prone) → 2d20kl1
  - NPC attacker Invisible advantage → 2d20kh1
  - Target condition advantage (Blinded / Paralyzed / Petrified /
    Restrained / Stunned / Unconscious) → 2d20kh1

With full RAW PHB p.173 cancel logic — adv + dis → straight 1d20 +
``canceled_*_vs_*`` label.

Seeding strategy: NPC condition buffs go directly on the NPC's
combatant.buffs list via PUT /battle (no sheet mirror needed —
the new helpers read hub state directly).

Tests:
  - NPC poisoned → 2d20kl1 + roll_state_applied =
    "disadvantage_attacker_poisoned".
  - NPC invisible → 2d20kh1 + roll_state_applied =
    "advantage_invisible".
  - NPC attacks Restrained PC → 2d20kh1 + roll_state_applied =
    "advantage_target_restrained".
  - NPC poisoned + target restrained → cancel per RAW PHB p.173 →
    single 1d20 + roll_state_applied starts with "canceled_".
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def pip_full(gm_client, roster):
    pip = roster["Pip Quickfingers"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/rest",
        json={"type": "long"},
    )
    return pip


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": combatants,
            "turn_index": 0,
            "round": 1,
            "active": True,
        },
    )


def _mkc(cid, char_id=None, hp_cur=30, hp_max=30, name="X", buffs=None,
         template_id=None):
    out = {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": hp_cur,
        "hp_max": hp_max,
        "buffs": buffs or [],
        "economy": {
            "action": False, "bonus": False,
            "reaction": False, "movement": 0,
        },
    }
    if template_id is not None:
        out["token_template_id"] = template_id
    return out


async def test_npc_attacker_poisoned_imposes_disadvantage(
    gm_client, pip_full,
):
    """NPC attacker carries a `poisoned` buff → /npc_attack's d20 drops
    to 2d20kl1 + roll_state_applied = 'disadvantage_attacker_poisoned'."""
    pip = pip_full
    pip_cid = f"tok_{pip['id']}"
    bandit_cid = "npc_p2c_poisoned_1"
    await _seed_battle(gm_client, [
        _mkc(
            bandit_cid, hp_cur=11, hp_max=11, name="Bandit",
            template_id=1,
            buffs=[{"key": "poisoned", "name": "Poisoned"}],
        ),
        _mkc(pip_cid, pip["id"], hp_cur=33, hp_max=33, name=pip["name"]),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/npc_attack",
        json={
            "combatant_id": bandit_cid,
            "action_name": "Scimitar",
            "attack_bonus": "+3",
            "damage": "1d6+1",
            "damage_type": "slashing",
            "target_combatant_id": pip_cid,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "2d20kl1" in (data.get("attack_breakdown") or ""), (
        f"Expected 2d20kl1; got attack_breakdown={data.get('attack_breakdown')!r}"
    )
    assert data.get("roll_state_applied") == "disadvantage_attacker_poisoned", (
        f"roll_state_applied mismatch; got {data.get('roll_state_applied')!r}"
    )


async def test_npc_attacker_invisible_grants_self_advantage(
    gm_client, pip_full,
):
    """NPC attacker carries an `invisible` buff → /npc_attack's d20
    rolls 2d20kh1 + roll_state_applied = 'advantage_invisible'."""
    pip = pip_full
    pip_cid = f"tok_{pip['id']}"
    bandit_cid = "npc_p2c_invisible_1"
    await _seed_battle(gm_client, [
        _mkc(
            bandit_cid, hp_cur=11, hp_max=11, name="Stalker",
            template_id=1,
            buffs=[{"key": "invisible", "name": "Invisible"}],
        ),
        _mkc(pip_cid, pip["id"], hp_cur=33, hp_max=33, name=pip["name"]),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/npc_attack",
        json={
            "combatant_id": bandit_cid,
            "action_name": "Bite",
            "attack_bonus": "+5",
            "damage": "1d8+3",
            "damage_type": "piercing",
            "target_combatant_id": pip_cid,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "2d20kh1" in (data.get("attack_breakdown") or "")
    assert data.get("roll_state_applied") == "advantage_invisible"


async def test_npc_attacks_restrained_target_gets_advantage(
    gm_client, pip_full,
):
    """NPC attacks a target carrying a `restrained` buff → /npc_attack's
    d20 rolls 2d20kh1 + roll_state_applied = 'advantage_target_restrained'."""
    pip = pip_full
    pip_cid = f"tok_{pip['id']}"
    bandit_cid = "npc_p2c_target_restr_1"
    await _seed_battle(gm_client, [
        _mkc(bandit_cid, hp_cur=11, hp_max=11, name="Bandit", template_id=1),
        _mkc(
            pip_cid, pip["id"], hp_cur=33, hp_max=33, name=pip["name"],
            buffs=[{"key": "restrained", "name": "Restrained"}],
        ),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/npc_attack",
        json={
            "combatant_id": bandit_cid,
            "action_name": "Scimitar",
            "attack_bonus": "+3",
            "damage": "1d6+1",
            "damage_type": "slashing",
            "target_combatant_id": pip_cid,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "2d20kh1" in (data.get("attack_breakdown") or "")
    assert data.get("roll_state_applied") == "advantage_target_restrained"


async def test_npc_adv_and_dis_cancel_per_raw(
    gm_client, pip_full,
):
    """RAW PHB p.173 — advantage + disadvantage cancel to a straight
    roll. NPC is poisoned (dis) AND target is restrained (adv) → single
    1d20 + roll_state_applied starts with 'canceled_'."""
    pip = pip_full
    pip_cid = f"tok_{pip['id']}"
    bandit_cid = "npc_p2c_cancel_1"
    await _seed_battle(gm_client, [
        _mkc(
            bandit_cid, hp_cur=11, hp_max=11, name="Bandit",
            template_id=1,
            buffs=[{"key": "poisoned", "name": "Poisoned"}],
        ),
        _mkc(
            pip_cid, pip["id"], hp_cur=33, hp_max=33, name=pip["name"],
            buffs=[{"key": "restrained", "name": "Restrained"}],
        ),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/npc_attack",
        json={
            "combatant_id": bandit_cid,
            "action_name": "Scimitar",
            "attack_bonus": "+3",
            "damage": "1d6+1",
            "damage_type": "slashing",
            "target_combatant_id": pip_cid,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    breakdown = data.get("attack_breakdown") or ""
    assert "2d20" not in breakdown, (
        f"Cancel should leave a single 1d20; got {breakdown!r}"
    )
    state = data.get("roll_state_applied") or ""
    assert state.startswith("canceled_"), (
        f"Expected canceled_*; got {state!r}"
    )
