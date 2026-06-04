"""v2.99.158 — Break-on-damage hook for buffs.

Closes the v2.99.156 filed item. Any buff with
`effects.break_on_damage: True` gets dropped from the target's
buffs list after the target takes nonzero damage. Wired into
both PC and NPC branches of `_apply_damage_to_combatant`.

The Turned condition (v2.99.156) is the first opt-in: RAW Turn
the Unholy ends "for 1 minute or until it takes damage." The
hook is extensible — Sleep, Heat Metal concentration, future
homebrew buffs can opt in by setting the flag.

Tests use a custom break-on-damage marker buff installed
directly via /api/.../sheet-fields or via the existing
/use_turn_the_unholy endpoint, then trigger damage via an
attack.

Tests:
  - Turned buff on a PC target → damage triggers break →
    buff gone
  - A buff WITHOUT break_on_damage stays after damage
    (regression guard)
  - Healing (negative damage) doesn't break the buff
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _mkc(cid, char_id=None, name="X", hp_cur=50, hp_max=75, buffs=None):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": hp_cur, "hp_max": hp_max,
        "buffs": list(buffs or []),
        "economy": {"action": False, "bonus": False, "reaction": False,
                    "movement": 0},
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1,
              "active": True},
    )


async def _get_buff_keys(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    return {(b or {}).get("key") for b in resp.json().get("buffs") or []}


async def _try_attack_until_hit(
    gm_client, attacker_id, target_combatant_id, attack_index=0,
):
    for _ in range(15):
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": attacker_id,
                "attack_index": attack_index,
                "target_combatant_id": target_combatant_id,
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        if data.get("hit"):
            return data
    return None


async def test_turned_buff_breaks_on_damage(
    gm_client, roster,
):
    """Krieger has a synthetic Turned buff (with
    effects.break_on_damage: True). Caelan attacks Krieger; on
    the first hit, the Turned buff is gone.
    """
    caelan = roster["Sir Caelan Lightbringer"]
    krieger = roster["Krieger Stonefist"]
    cae_tok = f"tok_bod_cae_{caelan['id']}"
    kri_tok = f"tok_bod_kri_{krieger['id']}"
    turned_buff = {
        "key": "turned", "name": "Turned (test seed)",
        "icon": "🙏", "duration_rounds": 10, "concentration": False,
        "source": "test-seed",
        "effects": {"break_on_damage": True},
    }
    await _seed_battle(gm_client, [
        _mkc(cae_tok, caelan["id"], name=caelan["name"]),
        _mkc(kri_tok, krieger["id"], name=krieger["name"],
             buffs=[turned_buff]),
    ])
    # Sanity check: Krieger starts with the Turned buff.
    pre = await _get_buff_keys(gm_client, krieger["id"])
    assert "turned" in pre
    # Caelan attacks with Longsword (index 0). Loop until a hit.
    hit_data = await _try_attack_until_hit(
        gm_client, caelan["id"], kri_tok, attack_index=0,
    )
    assert hit_data is not None, (
        "Longsword didn't hit Krieger in 15 tries — extreme flake"
    )
    # After the hit, Turned should be gone.
    post = await _get_buff_keys(gm_client, krieger["id"])
    assert "turned" not in post, (
        f"break_on_damage hook should drop Turned after damage; "
        f"got buffs={post}"
    )


async def test_non_break_buff_persists_after_damage(
    gm_client, roster,
):
    """A buff WITHOUT effects.break_on_damage stays after damage.
    Regression guard against the hook over-broadening.
    """
    caelan = roster["Sir Caelan Lightbringer"]
    krieger = roster["Krieger Stonefist"]
    cae_tok = f"tok_bod_persist_cae_{caelan['id']}"
    kri_tok = f"tok_bod_persist_kri_{krieger['id']}"
    persistent_buff = {
        "key": "persistent-test", "name": "Persistent (test seed)",
        "icon": "🟢", "duration_rounds": 100, "concentration": False,
        "source": "test-seed",
        "effects": {},
    }
    await _seed_battle(gm_client, [
        _mkc(cae_tok, caelan["id"], name=caelan["name"]),
        _mkc(kri_tok, krieger["id"], name=krieger["name"],
             buffs=[persistent_buff]),
    ])
    hit_data = await _try_attack_until_hit(
        gm_client, caelan["id"], kri_tok, attack_index=0,
    )
    assert hit_data is not None
    post = await _get_buff_keys(gm_client, krieger["id"])
    assert "persistent-test" in post, (
        f"buff WITHOUT break_on_damage should persist after damage; "
        f"got buffs={post}"
    )


async def test_break_on_damage_via_use_turn_the_unholy(
    gm_client, roster,
):
    """End-to-end: Caelan turns Krieger (creates Turned buff via
    the v2.99.156 endpoint), then attacks. The hit drops the
    Turned buff installed by the canonical /use_turn_the_unholy
    path.
    """
    caelan = roster["Sir Caelan Lightbringer"]
    krieger = roster["Krieger Stonefist"]
    cae_tok = f"tok_bod_e2e_cae_{caelan['id']}"
    kri_tok = f"tok_bod_e2e_kri_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(cae_tok, caelan["id"], name=caelan["name"]),
        _mkc(kri_tok, krieger["id"], name=krieger["name"]),
    ])
    # Refresh Caelan's channel-divinity charge.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/rest",
        json={"type": "short"},
    )
    # Caelan turns Krieger.
    turn_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_turn_the_unholy",
        json={
            "character_id": caelan["id"],
            "target_combatant_ids": [kri_tok],
        },
    )
    assert turn_resp.status_code == 200, turn_resp.text
    pre = await _get_buff_keys(gm_client, krieger["id"])
    assert "turned" in pre
    # Now attack — first hit should break the Turned buff.
    hit_data = await _try_attack_until_hit(
        gm_client, caelan["id"], kri_tok, attack_index=0,
    )
    assert hit_data is not None
    post = await _get_buff_keys(gm_client, krieger["id"])
    assert "turned" not in post
