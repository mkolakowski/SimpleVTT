"""v2.99.201 — Brutal Critical (Barbarian Lv 9 / 13 / 17).

Phase F.1 of the v2.99.193 phased completion plan. RAW (PHB
p.49): "Beginning at 9th level, you can roll one additional
weapon damage die when determining the extra damage for a
critical hit with a melee attack. This increases to two
additional dice at 13th level and three additional dice at 17th
level."

Wired alongside Savage Attacks in `_compute_attack_auto_uplifts`
(same gates: is_crit + weapon_damage_expr + is_physical melee).
Composes with Savage Attacks — a Half-Orc Barbarian gets BOTH
on a crit.

Tests use deterministic damage dice via the v2.99.13 dice-seed
endpoint; Krieger Stonefist (Half-Orc Berserker) gets bumped Lv 7
→ 9 / 13 / 17 via PATCH capstone-test convention.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _seed_dice(gm_client, seed: int):
    r = await gm_client.post(
        "/api/test/dice/seed", json={"seed": seed},
    )
    assert r.status_code == 200, r.text


async def _patch_sheet(gm_client, char_id, fields, class_slug=None):
    body = dict(fields)
    if class_slug:
        body["class_slug"] = class_slug
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json=body,
    )
    assert r.status_code == 200, r.text


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


def _tok(char):
    return {
        "id": f"tok_bc_{char['id']}",
        "char_id": char["id"],
        "name": char["name"],
        "initiative": 10,
        "hp_current": 50, "hp_max": 50,
        "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _swing_until_crit(
    gm_client, attacker_char_id, attack_index, target_combatant_id,
    *, attempts=40,
):
    """Repeatedly /attack until is_crit comes back True. Returns
    the response data dict. Used to bypass the random nat 20 gate
    without modifying the attack endpoint.
    """
    import asyncio
    for s in range(attempts):
        await _seed_dice(gm_client, 10000 + s)
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": attacker_char_id,
                "attack_index": attack_index,
                "target_combatant_id": target_combatant_id,
                "override": True,
            },
        )
        if r.status_code != 200:
            continue
        data = r.json()
        if data.get("is_crit"):
            return data
    raise AssertionError("No crit in attempts; bump seed range")


async def test_brutal_critical_lv9_one_extra_die(
    gm_client, roster,
):
    """Krieger PATCH'd to Lv 9 → crit with Greataxe → auto_uplifts
    contains a brutal-critical entry with `expression=1d12`
    (Greataxe damage die) and total in [1, 12].
    """
    krieger = roster["Krieger Stonefist"]
    pre_level = 7
    await _patch_sheet(
        gm_client, krieger["id"], {"level": 9},
        class_slug="barbarian",
    )
    try:
        pip = roster["Pip Quickfingers"]
        kr_tok = f"tok_bc_{krieger['id']}"
        pip_tok = f"tok_bc_{pip['id']}"
        await _seed_battle(gm_client, [_tok(krieger), _tok(pip)])
        data = await _swing_until_crit(
            gm_client, krieger["id"],
            attack_index=0,  # Greataxe (1d12)
            target_combatant_id=pip_tok,
        )
        bc = [u for u in data.get("auto_uplifts") or []
              if u.get("source") == "brutal-critical"]
        assert len(bc) == 1, (
            f"v2.99.201: expected exactly 1 brutal-critical entry; "
            f"got {bc} | full uplifts={data.get('auto_uplifts')}"
        )
        assert bc[0]["expression"] == "1d12"
        assert 1 <= bc[0]["total"] <= 12
        assert "+1 die" in bc[0]["label"]
    finally:
        await _patch_sheet(
            gm_client, krieger["id"], {"level": pre_level},
            class_slug="barbarian",
        )


async def test_brutal_critical_lv13_two_extra_dice(
    gm_client, roster,
):
    """Krieger Lv 13 → +2 extra dice (2d12)."""
    krieger = roster["Krieger Stonefist"]
    pre_level = 7
    await _patch_sheet(
        gm_client, krieger["id"], {"level": 13},
        class_slug="barbarian",
    )
    try:
        pip = roster["Pip Quickfingers"]
        kr_tok = f"tok_bc_{krieger['id']}"
        pip_tok = f"tok_bc_{pip['id']}"
        await _seed_battle(gm_client, [_tok(krieger), _tok(pip)])
        data = await _swing_until_crit(
            gm_client, krieger["id"],
            attack_index=0, target_combatant_id=pip_tok,
        )
        bc = [u for u in data.get("auto_uplifts") or []
              if u.get("source") == "brutal-critical"]
        assert len(bc) == 1
        assert bc[0]["expression"] == "2d12"
        assert 2 <= bc[0]["total"] <= 24
        assert "+2 dies" in bc[0]["label"]
    finally:
        await _patch_sheet(
            gm_client, krieger["id"], {"level": pre_level},
            class_slug="barbarian",
        )


async def test_brutal_critical_skips_below_lv9(
    gm_client, roster,
):
    """Control: Krieger at Lv 7 (default) → no brutal-critical
    uplift on crit (gate is Lv >= 9).
    """
    krieger = roster["Krieger Stonefist"]
    pip = roster["Pip Quickfingers"]
    pip_tok = f"tok_bc_{pip['id']}"
    await _seed_battle(gm_client, [_tok(krieger), _tok(pip)])
    data = await _swing_until_crit(
        gm_client, krieger["id"],
        attack_index=0, target_combatant_id=pip_tok,
    )
    bc = [u for u in data.get("auto_uplifts") or []
          if u.get("source") == "brutal-critical"]
    assert not bc, (
        f"v2.99.201: Brutal Critical shouldn't fire at Lv 7; "
        f"got {bc}"
    )


async def test_brutal_critical_skips_non_crit(
    gm_client, roster,
):
    """Control: Krieger Lv 9 makes a non-crit hit → no brutal-
    critical uplift (gate requires is_crit).
    """
    krieger = roster["Krieger Stonefist"]
    pip = roster["Pip Quickfingers"]
    pip_tok = f"tok_bc_{pip['id']}"
    pre_level = 7
    await _patch_sheet(
        gm_client, krieger["id"], {"level": 9},
        class_slug="barbarian",
    )
    try:
        await _seed_battle(gm_client, [_tok(krieger), _tok(pip)])
        # One non-crit swing: seed=1 typically gives a non-20.
        await _seed_dice(gm_client, 1)
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": krieger["id"],
                "attack_index": 0,
                "target_combatant_id": pip_tok,
                "override": True,
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()
        if data.get("is_crit"):
            # Unlucky — try a few more seeds for a non-crit.
            for s in range(2, 20):
                await _seed_dice(gm_client, s)
                r = await gm_client.post(
                    f"/api/campaign/{CAMPAIGN_ID}/attack",
                    json={
                        "character_id": krieger["id"],
                        "attack_index": 0,
                        "target_combatant_id": pip_tok,
                        "override": True,
                    },
                )
                if r.status_code == 200 and not r.json().get("is_crit"):
                    data = r.json()
                    break
        assert not data.get("is_crit")
        bc = [u for u in data.get("auto_uplifts") or []
              if u.get("source") == "brutal-critical"]
        assert not bc, (
            f"v2.99.201: Brutal Critical shouldn't fire on non-crit; "
            f"got {bc}"
        )
    finally:
        await _patch_sheet(
            gm_client, krieger["id"], {"level": pre_level},
            class_slug="barbarian",
        )
