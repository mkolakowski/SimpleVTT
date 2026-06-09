"""Phase 2f — NPC condition-driven disadvantage on /api/campaign/{cid}/roll.

Phase 2b (v2.153.0) gave PC `/roll` condition disadvantage via
`_roll_condition_disadvantage` reading PC `_buffs_active`. NPCs roll
through the same /roll endpoint with `skip_roll_state=True` and (as of
v2.157.0) a new `combatant_id` body field that lets the server look up
the NPC's `combatant.buffs` from hub state.

The new `_npc_roll_condition_disadvantage(campaign_id, combatant_id,
stat_key_lc, stat_ability)` helper mirrors the PC version's rule set:
  - Poisoned + Frightened → disadvantage on ability checks
  - Restrained → disadvantage on DEX saves

The PC fallback in /roll only fires when the PC path doesn't —
the two paths are mutually exclusive (PC has `_char`, NPC has
`skip_roll_state` + `combatant_id`).

Client-side: the unified mini-sheet's NPC stat-block buttons in
`app/templates/tabletop.html` now stamp `combatant_id` into the
POST body when the click came from an init-tracker entry (the slot
id is the combatant id). Template-browser monster clicks
(charIdRaw starts with 'monster-') deliberately don't pass it —
they have no associated combatant.

Tests:
  - NPC poisoned + /roll for str_check → 2d20kl1 +
    roll_state_applied = 'auto_disadvantage_poisoned'.
  - NPC frightened + /roll for str_check → same.
  - Control: NPC without buffs + /roll for str_check → 1d20.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": combatants,
            "turn_index": 0, "round": 1, "active": True,
        },
    )


def _mkc_npc(cid, name="Bandit", buffs=None, template_id=1):
    return {
        "id": cid, "char_id": None,
        "token_template_id": template_id,
        "name": name, "initiative": 10,
        "hp_current": 30, "hp_max": 30,
        "buffs": buffs or [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def test_npc_poisoned_check_imposes_disadvantage(gm_client):
    """NPC bandit carries a Poisoned buff → /roll for str_check (with
    combatant_id + skip_roll_state) returns 2d20kl1 with
    roll_state_applied = 'auto_disadvantage_poisoned'."""
    bandit_cid = "tok_p2f_poisoned_bandit"
    await _seed_battle(gm_client, [
        _mkc_npc(
            bandit_cid, name="Bandit",
            buffs=[{"key": "poisoned", "name": "Poisoned"}],
        ),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20",
            "skip_roll_state": True,
            "combatant_id": bandit_cid,
            "stat_key": "str_check",
            "stat_ability": "STR",
            "actor_name": "Bandit",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "2d20kl1" in (data.get("breakdown") or ""), (
        f"Expected 2d20kl1; got breakdown={data.get('breakdown')!r}"
    )
    assert data.get("roll_state_applied") == "auto_disadvantage_poisoned", (
        f"roll_state_applied mismatch; got {data.get('roll_state_applied')!r}"
    )


async def test_npc_frightened_check_imposes_disadvantage(gm_client):
    """NPC carries Frightened → /roll for ability check rolls 2d20kl1."""
    bandit_cid = "tok_p2f_frightened_bandit"
    await _seed_battle(gm_client, [
        _mkc_npc(
            bandit_cid, name="Bandit",
            buffs=[{"key": "frightened", "name": "Frightened"}],
        ),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20",
            "skip_roll_state": True,
            "combatant_id": bandit_cid,
            "stat_key": "wis_check",
            "stat_ability": "WIS",
            "actor_name": "Bandit",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "2d20kl1" in (data.get("breakdown") or "")
    assert data.get("roll_state_applied") == "auto_disadvantage_frightened"


async def test_npc_no_buff_check_unchanged(gm_client):
    """Control: NPC with no condition buffs rolls a normal 1d20."""
    bandit_cid = "tok_p2f_clean_bandit"
    await _seed_battle(gm_client, [
        _mkc_npc(bandit_cid, name="Bandit", buffs=[]),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20",
            "skip_roll_state": True,
            "combatant_id": bandit_cid,
            "stat_key": "str_check",
            "stat_ability": "STR",
            "actor_name": "Bandit",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "2d20kl1" not in (data.get("breakdown") or "")
    assert data.get("roll_state_applied") in (None, "")


async def test_npc_restrained_dex_save_imposes_disadvantage(gm_client):
    """NPC carries Restrained → /roll for dex_save rolls 2d20kl1."""
    bandit_cid = "tok_p2f_restrained_bandit"
    await _seed_battle(gm_client, [
        _mkc_npc(
            bandit_cid, name="Bandit",
            buffs=[{"key": "restrained", "name": "Restrained"}],
        ),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20",
            "skip_roll_state": True,
            "combatant_id": bandit_cid,
            "stat_key": "dex_save",
            "stat_ability": "DEX",
            "actor_name": "Bandit",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "2d20kl1" in (data.get("breakdown") or "")
    assert data.get("roll_state_applied") == "auto_disadvantage_restrained"
