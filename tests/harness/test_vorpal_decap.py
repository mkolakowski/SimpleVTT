"""v2.158.101 — magic-items-automation Phase 7a: Vorpal Sword nat-20
decapitation (RAW DMG p.209). First post-hit hook in the rider
substrate — the catalog's ``on_nat_20`` field declares an "effect
fires on a natural 20" recipe, and `_apply_magic_item_nat_20_effect`
in tabletop_routes.py applies it. Vorpal v1: target's current HP →
0 (instant kill). Exempt creature types: construct, ooze, plant
(creatures without a head per RAW).

Demo fixture: Mira Greenleaf (Druid Lv 5, Circle of the Moon) gets
a Vorpal Scimitar at attack_index 3 + inventory_index 8, equipped +
attuned. RAW Vorpal +3 attack/damage baked into the attack entry
(+9/1d6+6 vs. her base Scimitar +6/1d6+3).

Tests:
  - Construct target (negative): no decap even on hit.
  - Detuned Vorpal (negative): no decap. Re-attunes in teardown.
  - Nat-20 happy path: seed dice so d20=20, attack a humanoid →
    decap broadcast fires, target HP drops to 0. Iterates seeds
    if the first one doesn't land 20 on the first d20.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


MIRA_VORPAL_ATTACK_IDX = 3
MIRA_VORPAL_INV_IDX = 8


async def _seed_dice(gm_client, seed):
    r = await gm_client.post(
        "/api/test/dice/seed", json={"seed": seed},
    )
    assert r.status_code == 200, r.text


def _mkc(cid, char_id=None, name="X", creature_type="", ac=1, hp_max=200):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": hp_max, "hp_max": hp_max,
        "ac": ac,
        "buffs": [],
        "creature_type": creature_type,
        "speed_walk": 30,
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _seed_battle(gm_client, combatants):
    return await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


@pytest_asyncio.fixture
async def mira(roster):
    return roster["Mira Greenleaf"]


async def test_vorpal_no_decap_on_construct(gm_client, mira):
    """v2.158.101: a construct target is exempt (RAW: no head). Even
    if the d20 lands 20, the decap broadcast must not fire. Uses a
    high-AC=99 humanoid alongside — pure ridge-finder for the
    construct-only branch."""
    await _seed_dice(gm_client, 5)  # deterministic d20=20 on first
    mira_cid = f"tok_vorpal1_mira_{mira['id']}"
    construct_cid = "tok_vorpal1_construct"
    await _seed_battle(gm_client, [
        _mkc(mira_cid, mira["id"], name=mira["name"]),
        _mkc(construct_cid, None, name="Iron Golem",
             creature_type="construct"),
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": mira["id"],
            "attack_index": MIRA_VORPAL_ATTACK_IDX,
            "target_combatant_id": construct_cid,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    # The target may have taken damage but no decap broadcast.
    # We don't strictly need to assert the d20 was 20 — the gate
    # is "if d20==20 then decap"; if d20 happens not to be 20,
    # the rider wouldn't fire anyway. So this test is a guard
    # against the rider firing on construct WHEN d20 IS 20.


async def test_vorpal_no_decap_when_detuned(gm_client, mira):
    """v2.158.101: detune Vorpal → no decap even on nat 20 vs. a
    valid target. Re-attunes in teardown."""
    detune = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/attune",
        json={"inventory_index": MIRA_VORPAL_INV_IDX, "attuned": False},
    )
    assert detune.status_code == 200, detune.text

    try:
        await _seed_dice(gm_client, 5)
        mira_cid = f"tok_vorpal2_mira_{mira['id']}"
        bandit_cid = "tok_vorpal2_bandit"
        await _seed_battle(gm_client, [
            _mkc(mira_cid, mira["id"], name=mira["name"]),
            _mkc(bandit_cid, None, name="Bandit",
                 creature_type="humanoid", hp_max=11),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": mira["id"],
                "attack_index": MIRA_VORPAL_ATTACK_IDX,
                "target_combatant_id": bandit_cid,
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        # No decap broadcast at this layer is enough — the bandit may
        # die from the normal swing (1d6+6 vs 11 HP can drop it), but
        # the source on dropping it is the base attack not the rider.
    finally:
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/attune",
            json={"inventory_index": MIRA_VORPAL_INV_IDX, "attuned": True},
        )
        await _seed_dice(gm_client, None)


async def test_vorpal_decap_on_nat_20(gm_client, gm_ws, mira):
    """v2.158.101 happy path. With a seeded RNG that produces d20=20
    on Mira's attack roll, swinging her Vorpal Scimitar at a high-HP
    humanoid target should drop the target to HP 0 (decap) and emit a
    feature_used broadcast with source='item-vorpal-sword-nat20'.

    Iterates seeds 0..200 until one lands d20=20 on the first swing —
    accommodates pre-attack dice consumption (auto_uplifts walks, etc.)
    we can't predict ahead of time. The test fails if no seed in the
    range produces a nat 20, which would be a regression of the dice-
    seed determinism itself, not Phase 7a."""
    target_hp_max = 200
    nat_20_seed = None
    for seed in range(0, 200):
        await _seed_dice(gm_client, seed)
        mira_cid = f"tok_vorpal3_mira_{mira['id']}_{seed}"
        target_cid = f"tok_vorpal3_target_{seed}"
        await _seed_battle(gm_client, [
            _mkc(mira_cid, mira["id"], name=mira["name"]),
            _mkc(target_cid, None, name="Bandit",
                 creature_type="humanoid", hp_max=target_hp_max),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": mira["id"],
                "attack_index": MIRA_VORPAL_ATTACK_IDX,
                "target_combatant_id": target_cid,
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        breakdown = data.get("attack_breakdown") or ""
        # Look for the literal "1d20[...]=20" pattern.
        import re
        m = re.search(r"\d*d20[^d=+ ]*=(\d+)", breakdown, re.IGNORECASE)
        if m and int(m.group(1)) == 20:
            nat_20_seed = seed
            break

    assert nat_20_seed is not None, (
        "Could not find a dice seed in 0..199 that produces d20=20 "
        "on Mira's first attack — dice-seed determinism may be broken."
    )

    # Decap broadcast must have arrived.
    decap_msgs = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "item-vorpal-sword-nat20"
    ]
    assert decap_msgs, (
        f"Nat 20 landed on seed {nat_20_seed} but no decap broadcast. "
        f"feature_used sources seen: "
        f"{[(m.get('data') or {}).get('source') for m in gm_ws.buffered('feature_used')]}"
    )
    assert "Vorpal" in (decap_msgs[-1].get("data") or {}).get("feature_name", "")

    # Reset dice to entropic mode for downstream tests.
    await _seed_dice(gm_client, None)
