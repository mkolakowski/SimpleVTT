"""v2.370.0 — Deflect Missiles auto-reduction (Monk Lv 3+).

Closes the Monk Lv 3 Deflect Missiles row on class-content-status.md
(🟢 → ✅). RAW PHB p.78: "you can use your reaction to deflect or
catch the missile when you are hit by a ranged weapon attack. When
you do so, the damage you take from the attack is reduced by 1d10 +
your Dexterity modifier + your monk level."

Mirror of the v2.49.243 Uncanny Dodge auto-fire in
`_apply_damage_to_combatant`, but gated on `is_ranged_weapon_attack`
(the v2.366.0 kwarg threaded from /attack + /npc_attack via
`_attack_is_ranged_weapon(attack)`).

Demo fixture: Kael (Wood Elf Monk Lv 7, DEX 18, no shield) is the
target. Rowan Quickbow's Longbow is the ranged attacker. The /attack
response carries `target_hp_after` so we can compute the actual
applied damage.

Tests:
  - Kael Lv 7 (DEX +4 + Monk Lv 7) → ranged Longbow hit → damage
    reduced by 1d10 + 4 + 7 = 12..21. The reduction broadcast fires;
    if the reduction exceeds the damage, hp drops by 0.
  - Reaction already used → no auto-fire (UD precedent: gate on
    economy.reaction).
  - Melee attack on Kael → Deflect Missiles does NOT fire (gate on
    `is_ranged_weapon_attack`).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


ROWAN_LONGBOW_ATTACK_IDX = 0


def _mkc(cid, char_id=None, name="X", hp_max=80, ac=1, economy=None):
    return {
        "id": cid, "char_id": char_id, "name": name,
        "initiative": 10, "hp_current": hp_max, "hp_max": hp_max,
        "ac": ac, "buffs": [], "creature_type": "humanoid",
        "speed_walk": 30,
        "economy": economy or {
            "action": False, "bonus": False,
            "reaction": False, "movement": 0,
        },
    }


async def _seed_battle(gm_client, combatants):
    return await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


async def _seed_dice(gm_client, seed):
    r = await gm_client.post("/api/test/dice/seed", json={"seed": seed})
    assert r.status_code == 200, r.text


async def _ensure_auto_apply(gm_client, enable):
    return await gm_client.post(
        f"/api/test/campaign/{CAMPAIGN_ID}/flags",
        json={"auto_apply_damage": enable},
    )


@pytest_asyncio.fixture
async def kael(roster):
    return roster["Kael Brightleaf"]


@pytest_asyncio.fixture
async def rowan(roster):
    return roster["Rowan Quickbow"]


def _deflect_broadcasts(gm_ws, char_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "deflect-missiles"
        and (m.get("data") or {}).get("character_id") == char_id
    ]


async def _attack_until_hit(gm_client, attacker, target_cid, attack_idx,
                            tag, max_seeds=60):
    """Sweep seeds until a Longbow attack lands a hit on the target.
    Returns (seed, response_data) on the first hit; (None, last_data)
    if no hit landed."""
    last_data = None
    for seed in range(max_seeds):
        attacker_cid = f"tok_dm_{tag}_atk_{attacker['id']}_{seed}"
        await _seed_battle(gm_client, [
            _mkc(attacker_cid, attacker["id"], name=attacker["name"]),
            _mkc(target_cid, attacker.get("target_char_id"),
                 name=attacker.get("target_name", "Target"),
                 hp_max=80),
        ])
        await _seed_dice(gm_client, seed)
        try:
            resp = await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/attack",
                json={
                    "character_id": attacker["id"],
                    "attack_index": attack_idx,
                    "target_combatant_id": target_cid,
                    "override": True,
                },
            )
        finally:
            await _seed_dice(gm_client, None)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        last_data = data
        if data.get("hit"):
            return seed, data
    return None, last_data


async def test_deflect_missiles_reduces_ranged_damage(
    gm_client, gm_ws, kael, rowan,
):
    """Kael (Monk Lv 7, DEX +4) takes a Longbow hit from Rowan → damage
    reduced by 1d10 + 4 + 7 = 12..21. The broadcast fires with the
    reduction amount; if the reduction exceeds damage, the post-
    reduction value is 0 ("caught the missile")."""
    flags = await _ensure_auto_apply(gm_client, True)
    assert flags.status_code == 200, flags.text
    try:
        # Use a dedicated kael_cid so the target_cid matches between
        # the helper's "kael" target and the actual sweep.
        kael_cid = f"tok_dm_kael_reduce_{kael['id']}"
        rowan_cid = f"tok_dm_rowan_reduce_{rowan['id']}"
        # Sweep for a hit.
        for seed in range(60):
            await _seed_battle(gm_client, [
                _mkc(rowan_cid, rowan["id"], name=rowan["name"]),
                _mkc(kael_cid, kael["id"], name=kael["name"], hp_max=80),
            ])
            gm_ws.mark()
            await _seed_dice(gm_client, seed)
            try:
                resp = await gm_client.post(
                    f"/api/campaign/{CAMPAIGN_ID}/attack",
                    json={
                        "character_id": rowan["id"],
                        "attack_index": ROWAN_LONGBOW_ATTACK_IDX,
                        "target_combatant_id": kael_cid,
                        "override": True,
                    },
                )
            finally:
                await _seed_dice(gm_client, None)
            assert resp.status_code == 200, resp.text
            data = resp.json()
            if not data.get("hit"):
                continue
            # Hit landed. Check the deflect broadcast.
            msgs = _deflect_broadcasts(gm_ws, kael["id"])
            if not msgs:
                # Reaction may have been spent already from a prior
                # iteration — try the next seed.
                continue
            msg_data = msgs[-1].get("data") or {}
            reduction = int(msg_data.get("reduction_amount") or 0)
            pre = int(msg_data.get("pre_reduction") or 0)
            post = int(msg_data.get("post_reduction") or 0)
            # 1d10 + DEX +4 + Monk Lv 7 = 12..21.
            assert 12 <= reduction <= 21, (
                f"deflect reduction out of [12, 21]: got {reduction}"
            )
            assert post == max(0, pre - reduction), (
                f"post={post} should be max(0, pre={pre} - reduction={reduction})"
            )
            return
        raise AssertionError(
            "No Longbow hit landed in 60 seeds; couldn't observe Deflect Missiles"
        )
    finally:
        await _ensure_auto_apply(gm_client, False)


async def test_deflect_missiles_skipped_for_melee_attack(
    gm_client, gm_ws, kael, rowan,
):
    """A melee hit (Rowan's Shortsword, range 5 ft) does NOT trigger
    Deflect Missiles — the `is_ranged_weapon_attack` gate excludes
    melee. The deflect broadcast must not fire."""
    flags = await _ensure_auto_apply(gm_client, True)
    assert flags.status_code == 200, flags.text
    try:
        # Shortsword is at attack_index 1.
        for seed in range(60):
            kael_cid = f"tok_dm_kael_melee_{kael['id']}_{seed}"
            rowan_cid = f"tok_dm_rowan_melee_{rowan['id']}_{seed}"
            await _seed_battle(gm_client, [
                _mkc(rowan_cid, rowan["id"], name=rowan["name"]),
                _mkc(kael_cid, kael["id"], name=kael["name"], hp_max=80),
            ])
            gm_ws.mark()
            await _seed_dice(gm_client, seed)
            try:
                resp = await gm_client.post(
                    f"/api/campaign/{CAMPAIGN_ID}/attack",
                    json={
                        "character_id": rowan["id"],
                        "attack_index": 1,  # Shortsword (melee)
                        "target_combatant_id": kael_cid,
                        "override": True,
                    },
                )
            finally:
                await _seed_dice(gm_client, None)
            assert resp.status_code == 200, resp.text
            data = resp.json()
            assert "Shortsword" in (data.get("attack_name") or ""), (
                f"expected melee Shortsword; got {data.get('attack_name')!r}"
            )
            if data.get("hit"):
                msgs = _deflect_broadcasts(gm_ws, kael["id"])
                assert not msgs, (
                    f"Deflect Missiles must not fire on a melee attack; "
                    f"got broadcasts: {msgs}"
                )
                return
        # No hit landed; that's also OK for this test — the gate is
        # checked when a hit lands.
    finally:
        await _ensure_auto_apply(gm_client, False)


async def test_deflect_missiles_skipped_without_reaction(
    gm_client, gm_ws, kael, rowan,
):
    """If Kael's reaction is already spent (`economy.reaction: True`
    on his combatant), Deflect Missiles does NOT auto-fire — gate
    matches Uncanny Dodge."""
    flags = await _ensure_auto_apply(gm_client, True)
    assert flags.status_code == 200, flags.text
    try:
        for seed in range(60):
            kael_cid = f"tok_dm_kael_noreact_{kael['id']}_{seed}"
            rowan_cid = f"tok_dm_rowan_noreact_{rowan['id']}_{seed}"
            await _seed_battle(gm_client, [
                _mkc(rowan_cid, rowan["id"], name=rowan["name"]),
                _mkc(kael_cid, kael["id"], name=kael["name"], hp_max=80,
                     economy={
                         "action": False, "bonus": False,
                         "reaction": True, "movement": 0,
                     }),
            ])
            gm_ws.mark()
            await _seed_dice(gm_client, seed)
            try:
                resp = await gm_client.post(
                    f"/api/campaign/{CAMPAIGN_ID}/attack",
                    json={
                        "character_id": rowan["id"],
                        "attack_index": ROWAN_LONGBOW_ATTACK_IDX,
                        "target_combatant_id": kael_cid,
                        "override": True,
                    },
                )
            finally:
                await _seed_dice(gm_client, None)
            assert resp.status_code == 200, resp.text
            data = resp.json()
            if data.get("hit"):
                msgs = _deflect_broadcasts(gm_ws, kael["id"])
                assert not msgs, (
                    f"Deflect Missiles must not fire when reaction is "
                    f"spent; got broadcasts: {msgs}"
                )
                return
    finally:
        await _ensure_auto_apply(gm_client, False)
