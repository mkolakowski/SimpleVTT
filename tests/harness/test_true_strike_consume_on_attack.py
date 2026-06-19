"""v2.449.0 — Phase 1.5 of ``docs/plans/cast-and-broadcast-tail.md``.

Generic consume-on-attack contract: a buff with
`effects.consume_on_attack: True` is dropped from the attacker after
the first /attack they make. Closes the v2.437.0 True Strike
RAW-bend (RAW: advantage on "your *first* attack roll" — the v1
buff persisted for 1 round and granted advantage on every attack).

This test verifies the contract end-to-end against True Strike:
  1. Magnus (Warlock) casts True Strike on Krieger.
  2. The buff is installed on Magnus with consume_on_attack: True.
  3. Magnus attacks Krieger.
  4. The buff is GONE from Magnus's combatant after the attack.

The contract is generic — any buff with `consume_on_attack: True`
will drop on the next /attack. True Strike is the canonical
consumer; Feinting Attack (which already names
`next_attack_advantage: true` in its broadcast) can opt in by
setting the same flag.
"""
from .conftest import CAMPAIGN_ID


async def _set_battle(gm_client, caster, target_combatant_id):
    pc_cb = {
        "id": f"tok_ts_consume_{caster['id']}",
        "char_id": caster["id"],
        "name": caster["name"],
        "initiative": 15,
        "hp_current": 30, "hp_max": 30,
        "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }
    target_cb = {
        "id": target_combatant_id, "char_id": None,
        "name": "TS Consume Target",
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
    return pc_cb["id"]


async def _get_buffs(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    assert r.status_code == 200, r.text
    return r.json().get("buffs") or []


async def test_true_strike_buff_consumed_after_first_attack(
    gm_client, roster,
):
    """Magnus casts True Strike, then attacks. The buff is dropped
    by the consume-on-attack contract — verified by polling
    /character/{id}/buffs before and after the attack."""
    magnus = roster["Magnus Hexbinder"]
    target_combatant_id = "tok_ts_consume_target_npc"
    await _set_battle(gm_client, magnus, target_combatant_id)

    # Cast True Strike on the NPC target.
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_true_strike",
        json={
            "character_id": magnus["id"],
            "target_combatant_id": target_combatant_id,
        },
    )
    assert cast.status_code == 200, cast.text
    assert cast.json()["buff_installed"] is True

    # Verify the buff has consume_on_attack: True (v2.449.0 contract).
    buffs_before = await _get_buffs(gm_client, magnus["id"])
    ts_buff = next(
        (b for b in buffs_before if b.get("key") == "true-strike"), None,
    )
    assert ts_buff is not None, (
        f"true-strike buff missing after cast: {buffs_before}"
    )
    effects = ts_buff.get("effects") or {}
    assert effects.get("consume_on_attack") is True, (
        f"True Strike's buff should opt into consume_on_attack; "
        f"got effects={effects}"
    )

    # Magnus attacks the marked target. The first attack consumes the
    # buff via the /attack endpoint's consume contract.
    atk = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": magnus["id"],
            "attack_index": 0,
            "target_combatant_id": target_combatant_id,
            "override": True,
        },
    )
    assert atk.status_code == 200, atk.text

    # Verify the buff is gone.
    buffs_after = await _get_buffs(gm_client, magnus["id"])
    ts_buff_after = next(
        (b for b in buffs_after if b.get("key") == "true-strike"), None,
    )
    assert ts_buff_after is None, (
        f"true-strike buff should be consumed by the first /attack; "
        f"got buffs={buffs_after}"
    )


async def test_attack_without_consume_on_attack_buff_no_op(
    gm_client, roster,
):
    """Sanity: an /attack with no consume-on-attack buff active is a
    no-op for the contract. Magnus attacks without True Strike → no
    buff drops + the attack returns normally."""
    magnus = roster["Magnus Hexbinder"]
    target_combatant_id = "tok_ts_consume_target_noop"
    await _set_battle(gm_client, magnus, target_combatant_id)

    buffs_before = await _get_buffs(gm_client, magnus["id"])
    # The fixture battle leaves Magnus with no buffs.
    assert not any(
        (b.get("effects") or {}).get("consume_on_attack")
        for b in buffs_before
    ), f"expected no consume-on-attack buffs at setup; got {buffs_before}"

    atk = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": magnus["id"],
            "attack_index": 0,
            "target_combatant_id": target_combatant_id,
            "override": True,
        },
    )
    assert atk.status_code == 200, atk.text
    assert atk.json().get("ok") is True
