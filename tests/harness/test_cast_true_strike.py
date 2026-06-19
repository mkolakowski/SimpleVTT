"""True Strike — Cantrip, Bard/Sorcerer/Warlock/Wizard. Phase 1
demonstrator #1 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.437.0 — RAW PHB p.284: "You extend your hand and point a
finger at a target in range. Your magic grants you a brief
insight into the target's defenses. On your next turn, you gain
advantage on your first attack roll against the target, provided
that this spell hasn't ended." Action, V/S/M (focus), 30 ft, 1
round, concentration.

Implementation rides the v2.158.53 generic
``_attacker_has_vow_of_enmity_vs_target`` helper — True Strike
installs a 1-round concentration buff with
``effects.attack_advantage_vs_target_combatant_id`` set to the
chosen target's combatant id, and the /attack endpoint's existing
read site picks it up without modification. The buff drops at end
of next turn (1-round duration) or when concentration breaks. No
new attack-pipeline hook in this commit.

RAW-bent v1: RAW says "*first* attack roll." This v1 grants
advantage on *every* attack against the marked target for the
buff's 1-round duration. Filed for Phase 1.5: a generic
buff-consume-on-hit contract.

Tests:
  - Cast installs the buff with the right effect + target binding.
  - The installed buff has concentration=true + duration_rounds=1.
  - A non-caster non-knower (Krieger Barbarian) gets 409 cannot_cast.
  - Cast without target_combatant_id → 400.
"""
import httpx

from .conftest import CAMPAIGN_ID
from .helpers import BASE_URL


async def _set_battle(gm_client, caster, target_combatant_id):
    """Stand up a tiny battle so the buff has a hub state to install
    into. Reuses the same shape as the existing cast-spell tests."""
    pc_cb = {
        "id": f"tok_caster_{caster['id']}",
        "char_id": caster["id"],
        "name": caster["name"],
        "initiative": 15,
        "hp_current": 30, "hp_max": 30,
        "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }
    target_cb = {
        "id": target_combatant_id, "char_id": None, "name": "TS Target",
        "initiative": 10,
        "hp_current": 50, "hp_max": 50,
        "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [pc_cb, target_cb], "turn_index": 0,
              "round": 1, "active": True},
    )


async def _get_caster_buffs(gm_client, caster_id):
    """Pull the caster's buffs via the per-character buffs endpoint."""
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caster_id}/buffs",
    )
    assert r.status_code == 200, r.text
    return r.json().get("buffs") or []


async def test_cast_true_strike_installs_buff_with_target_binding(gm_client, roster):
    """Thalindra Moonwhisper (Wizard) casts True Strike on a target;
    the buff carries effects.attack_advantage_vs_target_combatant_id
    bound to the target combatant id."""
    thalindra = roster["Thalindra Moonwhisper"]
    target_id = "tok_ts_test_target"
    await _set_battle(gm_client, thalindra, target_id)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_true_strike",
        json={"character_id": thalindra["id"],
              "target_combatant_id": target_id},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "true-strike"
    assert body["target_combatant_id"] == target_id
    assert body["buff_installed"] is True

    buffs = await _get_caster_buffs(gm_client, thalindra["id"])
    ts_buff = next((b for b in buffs if b.get("key") == "true-strike"), None)
    assert ts_buff is not None, f"true-strike buff missing from caster: {buffs}"
    effects = ts_buff.get("effects") or {}
    assert effects.get("attack_advantage_vs_target_combatant_id") == target_id


async def test_cast_true_strike_buff_is_concentration_one_round(gm_client, roster):
    """The installed buff carries concentration=true and the 1-round
    duration RAW prescribes."""
    thalindra = roster["Thalindra Moonwhisper"]
    target_id = "tok_ts_concent_target"
    await _set_battle(gm_client, thalindra, target_id)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_true_strike",
        json={"character_id": thalindra["id"],
              "target_combatant_id": target_id},
    )
    assert r.status_code == 200, r.text
    buffs = await _get_caster_buffs(gm_client, thalindra["id"])
    ts_buff = next((b for b in buffs if b.get("key") == "true-strike"), None)
    assert ts_buff is not None
    assert ts_buff.get("concentration") is True
    assert int(ts_buff.get("duration_rounds") or 0) == 1


async def test_cast_true_strike_non_caster_rejected(gm_client, roster):
    """Krieger Stonefist is a Barbarian (not in the
    Bard/Sorcerer/Warlock/Wizard caster list); the cast endpoint
    returns 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    target_id = "tok_ts_krieger_target"
    await _set_battle(gm_client, krieger, target_id)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_true_strike",
        json={"character_id": krieger["id"],
              "target_combatant_id": target_id},
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["error"] == "cannot_cast"
    assert "true strike" in body["expected"].lower()


async def test_cast_true_strike_missing_target_400(gm_client, roster):
    """target_combatant_id is required; omitting it returns 400."""
    thalindra = roster["Thalindra Moonwhisper"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_true_strike",
        json={"character_id": thalindra["id"]},
    )
    assert r.status_code == 400, r.text
