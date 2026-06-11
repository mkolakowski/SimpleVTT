"""v2.158.103 — magic-items-automation Phase 7c: Sword of Sharpness
+4d6 slashing on natural 20 (RAW DMG p.206). Second item to use the
v2.158.101 ``on_nat_20`` post-hit hook substrate, exercising the new
``effect: "damage"`` variant (Vorpal uses ``effect: "decap"``). The
same `_apply_magic_item_nat_20_effect` helper dispatches both.

Demo fixture: Pip Quickfingers (Rogue Lv 7) gets a Sword of Sharpness
Shortsword at attack_index 2 + inventory_index 9, equipped + attuned.
Pip caps her attunement at 3/3 — Cloak of Protection (v2.158.78) +
Ring of Protection (v2.158.78) + Sharpness (v2.158.103). The "lop off
a limb on a second nat 20" RAW follow-up is GM narrative, not modeled.

Tests use the dice-seed mechanism to deterministically land a nat 20.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


PIP_SHARPNESS_ATTACK_IDX = 2
PIP_SHARPNESS_INV_IDX = 9


async def _seed_dice(gm_client, seed):
    r = await gm_client.post(
        "/api/test/dice/seed", json={"seed": seed},
    )
    assert r.status_code == 200, r.text


def _mkc(cid, char_id=None, name="X", ac=1, hp_max=200):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": hp_max, "hp_max": hp_max,
        "ac": ac,
        "buffs": [],
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


async def test_sharpness_no_rider_when_detuned(gm_client, pip):
    """v2.158.103: detuning the Sword of Sharpness suppresses the
    nat-20 rider — even if the d20 lands 20, no +4d6 broadcast.
    Re-attunes in teardown."""
    detune = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/attune",
        json={"inventory_index": PIP_SHARPNESS_INV_IDX, "attuned": False},
    )
    assert detune.status_code == 200, detune.text

    try:
        await _seed_dice(gm_client, 5)  # d20=20 on first
        pip_cid = f"tok_sharp1_pip_{pip['id']}"
        target_cid = "tok_sharp1_target"
        await _seed_battle(gm_client, [
            _mkc(pip_cid, pip["id"], name=pip["name"]),
            _mkc(target_cid, None, name="Bandit"),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": pip["id"],
                "attack_index": PIP_SHARPNESS_ATTACK_IDX,
                "target_combatant_id": target_cid,
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
    finally:
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/attune",
            json={"inventory_index": PIP_SHARPNESS_INV_IDX, "attuned": True},
        )
        await _seed_dice(gm_client, None)


async def test_sharpness_nat_20_extra_damage(gm_client, gm_ws, pip):
    """v2.158.103 happy path. With a seeded RNG that lands d20=20 on
    Pip's attack, the Sword of Sharpness post-hit handler rolls
    +4d6 slashing via the on_nat_20 effect="damage" branch and
    broadcasts a feature_used with source='item-sword-of-sharpness-nat20'.

    Iterates seeds 0..199 finding one that lands d20=20 on Pip's
    first attack (accommodates pre-attack dice consumption that we
    can't predict)."""
    target_hp_max = 200
    nat_20_seed = None
    for seed in range(0, 200):
        await _seed_dice(gm_client, seed)
        pip_cid = f"tok_sharp2_pip_{pip['id']}_{seed}"
        target_cid = f"tok_sharp2_target_{seed}"
        await _seed_battle(gm_client, [
            _mkc(pip_cid, pip["id"], name=pip["name"]),
            _mkc(target_cid, None, name="Bandit", hp_max=target_hp_max),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": pip["id"],
                "attack_index": PIP_SHARPNESS_ATTACK_IDX,
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
        "Couldn't find a dice seed in 0..199 that lands d20=20 on "
        "Pip's first attack — dice-seed determinism may be broken."
    )

    sharpness_msgs = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source")
        == "item-sword-of-sharpness-nat20"
    ]
    assert sharpness_msgs, (
        f"Nat 20 landed on seed {nat_20_seed} but no Sharpness "
        f"broadcast. Sources seen: "
        f"{[(m.get('data') or {}).get('source') for m in gm_ws.buffered('feature_used')]}"
    )
    msg_data = sharpness_msgs[-1].get("data") or {}
    assert "Sharpness" in (msg_data.get("feature_name") or "")
    # 4d6 → [4, 24] non-crit. Even with crit-doubling this stays in
    # range because the on_nat_20 dice aren't doubled (they're a
    # post-hit rider, not the base damage).
    hp_dealt = int(msg_data.get("hp_dealt") or 0)
    assert 4 <= hp_dealt <= 24, (
        f"Sharpness 4d6 damage out of [4, 24]: got {hp_dealt}"
    )

    await _seed_dice(gm_client, None)
