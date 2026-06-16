"""v2.364.0 — magic-items: Adamantine Armor (RAW DMG p.150, uncommon,
NO attunement). The clean mechanical effect: "When you wear this
armor, any critical hit against you becomes a normal hit." Folded
into `_equipped_item_effects` via the new `crits_become_normal`
field; the /attack and /npc_attack pipelines call
`_target_wearer_crits_become_normal` after the is_crit determination
and, when True, flip `is_crit` back to False BEFORE the damage-dice
doubling. The suppression is announced via a `feature_used`
broadcast (source `item-adamantine-armor-crit-suppressed`).

Demo fixture: Garrik Ironside (Fighter Lv 9, chain mail AC 16)
carries the Adamantine Armor as inert Armory's Remainder vault loot;
the harness PATCHes it equipped (no attunement RAW). Sir Caelan
attacks Garrik with his standard +6 / 1d8+3 longsword; seed sweep
0..199 finds a seed where the first d20 lands a natural 20.

Tests:
  - With the armor equipped → on a seed that rolls d20=20, the
    response carries `is_crit: False` AND `adamantine_crit_suppressed:
    True`; a `feature_used` audit broadcast fires with source
    `item-adamantine-armor-crit-suppressed`.
  - With the armor NOT equipped → on the same nat-20 seed, the
    response carries `is_crit: True` and no suppression broadcast
    fires (proves the gate is armor-sourced, not baked).
"""
import re

import pytest_asyncio

from .conftest import CAMPAIGN_ID


CAELAN_LONGSWORD_ATTACK_IDX = 0  # base Longsword
_SLUG = "adamantine-armor"
_SUPPRESS_SOURCE = "item-adamantine-armor-crit-suppressed"


async def _seed_dice(gm_client, seed):
    r = await gm_client.post("/api/test/dice/seed", json={"seed": seed})
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
        "creature_type": "humanoid",
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


async def _snapshot_inv(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    inv = list(((resp.json() or {}).get("sheet") or {}).get("inventory") or [])
    return [dict(it) if isinstance(it, dict) else it for it in inv]


async def _patch_armor(gm_client, char_id, *, equipped):
    snapshot = await _snapshot_inv(gm_client, char_id)
    new_inv = [dict(it) if isinstance(it, dict) else it for it in snapshot]
    found = False
    for it in new_inv:
        if isinstance(it, dict) and it.get("_slug") == _SLUG:
            it["equipped"] = equipped
            found = True
    assert found, "Garrik has no adamantine-armor inventory item"
    resp = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"inventory": new_inv},
    )
    assert resp.status_code == 200, resp.text
    return snapshot


async def _restore_inv(gm_client, char_id, snapshot):
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"inventory": snapshot},
    )


def _d20_kept(breakdown):
    """Extract the d20 kept value from an attack breakdown string."""
    m = re.search(r"\d*d20[^d=+ ]*=(\d+)", breakdown or "", re.IGNORECASE)
    return int(m.group(1)) if m else None


async def _attack_until_nat_20(gm_client, attacker, target_cid, target_pc_id,
                               target_ac, attack_idx, tag, max_seeds=200):
    """Sweep seeds until Caelan's first d20 rolls a 20 vs the target. Returns
    (seed, response_data) for the first nat-20 attack."""
    for seed in range(0, max_seeds):
        attacker_cid = f"tok_ad_{tag}_caelan_{attacker['id']}_{seed}"
        await _seed_battle(gm_client, [
            _mkc(attacker_cid, attacker["id"], name=attacker["name"]),
            _mkc(target_cid, target_pc_id, name="Garrik", ac=target_ac),
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
        if _d20_kept(data.get("attack_breakdown") or "") == 20:
            return seed, data
    return None, None


@pytest_asyncio.fixture
async def caelan(roster):
    return roster["Sir Caelan Lightbringer"]


@pytest_asyncio.fixture
async def garrik(roster):
    return roster["Garrik Ironside"]


async def test_adamantine_suppresses_crit(gm_client, gm_ws, caelan, garrik):
    """Armor equipped → on a seed that rolls d20=20, the /attack response
    flips `is_crit` to False + sets `adamantine_crit_suppressed: True` +
    fires a `feature_used` audit with source
    `item-adamantine-armor-crit-suppressed`."""
    snap = await _patch_armor(gm_client, garrik["id"], equipped=True)
    try:
        target_cid = f"tok_ad_supp_garrik_{garrik['id']}"
        seed, data = await _attack_until_nat_20(
            gm_client, caelan, target_cid, garrik["id"],
            target_ac=10, attack_idx=CAELAN_LONGSWORD_ATTACK_IDX,
            tag="supp",
        )
        assert seed is not None, (
            "no seed in 0..199 produced a d20=20 on Caelan's first attack — "
            "dice-seed determinism may be broken."
        )
        assert data.get("is_crit") is False, (
            f"adamantine should have flipped is_crit to False; got "
            f"is_crit={data.get('is_crit')!r} on seed {seed}"
        )
        assert data.get("adamantine_crit_suppressed") is True, (
            f"expected adamantine_crit_suppressed=True; got "
            f"{data.get('adamantine_crit_suppressed')!r}"
        )
        assert data.get("adamantine_crit_suppressor") == "Adamantine Armor"
        # `feature_used` audit broadcast fired.
        msgs = [
            m for m in gm_ws.buffered("feature_used")
            if (m.get("data") or {}).get("source") == _SUPPRESS_SOURCE
        ]
        assert msgs, (
            f"expected an item-adamantine-armor-crit-suppressed broadcast; "
            f"sources seen: "
            f"{[(m.get('data') or {}).get('source') for m in gm_ws.buffered('feature_used')]}"
        )
    finally:
        await _restore_inv(gm_client, garrik["id"], snap)


async def test_no_suppression_without_armor(gm_client, gm_ws, caelan, garrik):
    """Armor NOT equipped (default seed inert) → on a seed that rolls
    d20=20, `is_crit` stays True and no suppression broadcast fires
    (proves the gate is armor-sourced, not baked)."""
    # No PATCH — leave the inventory at seed state (armor inert).
    target_cid = f"tok_ad_nosupp_garrik_{garrik['id']}"
    seed, data = await _attack_until_nat_20(
        gm_client, caelan, target_cid, garrik["id"],
        target_ac=10, attack_idx=CAELAN_LONGSWORD_ATTACK_IDX,
        tag="nosupp",
    )
    assert seed is not None, (
        "no seed in 0..199 produced a d20=20 on Caelan's first attack"
    )
    assert data.get("is_crit") is True, (
        f"without armor, a nat-20 should crit; got is_crit="
        f"{data.get('is_crit')!r} on seed {seed}"
    )
    assert data.get("adamantine_crit_suppressed") in (False, None), (
        f"unexpected suppression flag without armor; got "
        f"{data.get('adamantine_crit_suppressed')!r}"
    )
    # The suppression `feature_used` broadcast must not appear for THIS
    # attack (other tests in the session may have queued earlier ones —
    # we filter by target id to scope the check).
    suppress_for_this = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == _SUPPRESS_SOURCE
        and (m.get("data") or {}).get("target_combatant_id") == target_cid
    ]
    assert suppress_for_this == [], (
        f"adamantine suppression fired without armor: {suppress_for_this!r}"
    )
