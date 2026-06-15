"""v2.318.0 — magic-items: Sword of Life Stealing (RAW DMG p.206, rare,
attunement). Third item on the on_nat_20 effect="damage" branch (Sword of
Sharpness v2.158.103 precedent), and the first to compose
`exempt_creature_types` with a damage rider — Vorpal Sword (v2.158.101) uses
the same exempt list but with effect="decap". On a natural 20 attack roll,
the target takes an extra 3d6 necrotic damage, provided the target isn't a
construct or undead. The same `_apply_magic_item_nat_20_effect` helper
dispatches all three items.

Demo fixture: Pip Quickfingers (Rogue Lv 7) gets a Sword of Life Stealing
Shortsword at attack_index 3 + inventory tail, equipped + attuned (her 5th
attuned item; seed-load bypasses the RAW 3-item cap, enforced only at
/attune runtime). The temp-HP-equal-to-extra-damage RAW clause is
GM-narrated in v1.

Tests use the dice-seed mechanism to deterministically land a nat 20:
  - Happy path: nat 20 vs humanoid → +3d6 necrotic broadcast, hp_dealt
    in [3, 18].
  - Construct exempt: nat 20 vs construct → no broadcast (gate fires
    before the damage roll).
  - Undead exempt: nat 20 vs undead → no broadcast.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


PIP_LIFE_STEAL_ATTACK_IDX = 3


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
async def pip(roster):
    return roster["Pip Quickfingers"]


async def test_life_stealing_no_rider_on_construct(gm_client, gm_ws, pip):
    """v2.318.0: construct target is exempt (RAW: undead/construct exempt).
    Even if the d20 lands 20, the +3d6 necrotic broadcast must NOT fire.
    Iterates seeds 0..199 finding one that lands d20=20 on Pip's first
    attack so this is a true positive control on the exemption gate."""
    nat_20_seed = None
    for seed in range(0, 200):
        await _seed_dice(gm_client, seed)
        pip_cid = f"tok_lifesteal_construct_pip_{pip['id']}_{seed}"
        target_cid = f"tok_lifesteal_construct_target_{seed}"
        await _seed_battle(gm_client, [
            _mkc(pip_cid, pip["id"], name=pip["name"]),
            _mkc(target_cid, None, name="Iron Golem",
                 creature_type="construct"),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": pip["id"],
                "attack_index": PIP_LIFE_STEAL_ATTACK_IDX,
                "target_combatant_id": target_cid,
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        breakdown = data.get("attack_breakdown") or ""
        import re
        m = re.search(r"\d*d20[^d=+ ]*=(\d+)", breakdown, re.IGNORECASE)
        if m and int(m.group(1)) == 20:
            nat_20_seed = seed
            break

    assert nat_20_seed is not None, (
        "Couldn't find a dice seed in 0..199 that lands d20=20 on Pip's "
        "first Life Stealing swing — dice-seed determinism may be broken."
    )

    # Construct target is exempt — no Life Stealing broadcast.
    life_steal_msgs = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source")
        == "item-sword-of-life-stealing-nat20"
    ]
    assert not life_steal_msgs, (
        f"Nat 20 landed on seed {nat_20_seed} vs a construct, but Life "
        f"Stealing rider fired anyway. Sources seen: "
        f"{[(m.get('data') or {}).get('source') for m in gm_ws.buffered('feature_used')]}"
    )

    await _seed_dice(gm_client, None)


async def test_life_stealing_no_rider_on_undead(gm_client, gm_ws, pip):
    """v2.318.0: undead target is exempt (RAW: undead/construct exempt).
    Same positive-control shape as the construct test — a real nat 20 lands
    and we assert the rider DIDN'T fire. Exercises the second exempt slot in
    the catalog row's `exempt_creature_types` list."""
    nat_20_seed = None
    for seed in range(0, 200):
        await _seed_dice(gm_client, seed)
        pip_cid = f"tok_lifesteal_undead_pip_{pip['id']}_{seed}"
        target_cid = f"tok_lifesteal_undead_target_{seed}"
        await _seed_battle(gm_client, [
            _mkc(pip_cid, pip["id"], name=pip["name"]),
            _mkc(target_cid, None, name="Skeleton",
                 creature_type="undead"),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": pip["id"],
                "attack_index": PIP_LIFE_STEAL_ATTACK_IDX,
                "target_combatant_id": target_cid,
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        breakdown = data.get("attack_breakdown") or ""
        import re
        m = re.search(r"\d*d20[^d=+ ]*=(\d+)", breakdown, re.IGNORECASE)
        if m and int(m.group(1)) == 20:
            nat_20_seed = seed
            break

    assert nat_20_seed is not None, (
        "Couldn't find a dice seed in 0..199 that lands d20=20 on Pip's "
        "first Life Stealing swing — dice-seed determinism may be broken."
    )

    life_steal_msgs = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source")
        == "item-sword-of-life-stealing-nat20"
    ]
    assert not life_steal_msgs, (
        f"Nat 20 landed on seed {nat_20_seed} vs an undead, but Life "
        f"Stealing rider fired anyway. Sources seen: "
        f"{[(m.get('data') or {}).get('source') for m in gm_ws.buffered('feature_used')]}"
    )

    await _seed_dice(gm_client, None)


async def test_life_stealing_nat_20_extra_damage(gm_client, gm_ws, pip):
    """v2.318.0 happy path. With a seeded RNG that lands d20=20 on Pip's
    attack, the Sword of Life Stealing post-hit handler rolls +3d6 necrotic
    via the on_nat_20 effect="damage" branch and broadcasts a feature_used
    with source='item-sword-of-life-stealing-nat20'.

    Iterates seeds 0..199 finding one that lands d20=20 on Pip's first
    attack (accommodates pre-attack dice consumption we can't predict).
    """
    target_hp_max = 200
    nat_20_seed = None
    for seed in range(0, 200):
        await _seed_dice(gm_client, seed)
        pip_cid = f"tok_lifesteal_hit_pip_{pip['id']}_{seed}"
        target_cid = f"tok_lifesteal_hit_target_{seed}"
        await _seed_battle(gm_client, [
            _mkc(pip_cid, pip["id"], name=pip["name"]),
            _mkc(target_cid, None, name="Bandit",
                 creature_type="humanoid", hp_max=target_hp_max),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": pip["id"],
                "attack_index": PIP_LIFE_STEAL_ATTACK_IDX,
                "target_combatant_id": target_cid,
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        breakdown = data.get("attack_breakdown") or ""
        import re
        m = re.search(r"\d*d20[^d=+ ]*=(\d+)", breakdown, re.IGNORECASE)
        if m and int(m.group(1)) == 20:
            nat_20_seed = seed
            break

    assert nat_20_seed is not None, (
        "Couldn't find a dice seed in 0..199 that lands d20=20 on Pip's "
        "first Life Stealing swing — dice-seed determinism may be broken."
    )

    life_steal_msgs = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source")
        == "item-sword-of-life-stealing-nat20"
    ]
    assert life_steal_msgs, (
        f"Nat 20 landed on seed {nat_20_seed} but no Life Stealing "
        f"broadcast. Sources seen: "
        f"{[(m.get('data') or {}).get('source') for m in gm_ws.buffered('feature_used')]}"
    )
    msg_data = life_steal_msgs[-1].get("data") or {}
    assert "Life Stealing" in (msg_data.get("feature_name") or "")
    # RAW 3d6 → [3, 18]. The rider dice aren't doubled on crit (the post-hit
    # rider rolls its own catalog dice, distinct from the base attack damage).
    hp_dealt = int(msg_data.get("hp_dealt") or 0)
    assert 3 <= hp_dealt <= 18, (
        f"Life Stealing 3d6 damage out of [3, 18]: got {hp_dealt}"
    )

    await _seed_dice(gm_client, None)
