"""v2.385.0 — Sneak Attack ally-adjacency now skips incapacitated allies.

RAW Sneak Attack (Rogue Lv 1): "another enemy of the target is within
5 feet of it, **not incapacitated**, and you don't have disadvantage
on the attack roll." The "not incapacitated" clause was filed in the
v2.62.1 advisory implementation (`tabletop_routes.py` line 3260 in the
v2.384.0 audit). v2.385.0 closes the gap via the new shared
`_combatant_is_incapacitated()` helper that reads the existing
`_INCAPACITATING_BUFF_KEYS` set (paralyzed / stunned / unconscious /
petrified / asleep / Hideous-Laughter).

This is clause #1 of the v2.384.0 condition-enforcement audit's
suggested per-clause shipping order.

Tests:
  - Pip attacks Krieger with Caelan placed 5 ft from Krieger, but
    Caelan carries the `paralyzed` buff → advisory False (the
    incapacitated ally doesn't count).
  - Same setup but Caelan carries a non-incapacitating buff
    (`bless` = key "bless") → advisory True (Bless doesn't
    disqualify; only the canonical incapacitating set does).
"""
from __future__ import annotations

import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def pip_rested(gm_client, roster):
    pip = roster["Pip Quickfingers"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/rest",
        json={"type": "long"},
    )
    return pip


def _make_combatant(name, char_id, hp_current=30, hp_max=50, init=10,
                    buffs=None):
    """Build a battle combatant; optional `buffs` injects pre-existing
    buffs on the combatant (the /battle PUT writes them as-is)."""
    return {
        "id": f"tok_sa_inc_{char_id}",
        "char_id": char_id,
        "name": name,
        "initiative": init,
        "hp_current": hp_current, "hp_max": hp_max,
        "buffs": buffs or [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


async def _place_token(gm_client, char_id, x, y):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/place-token",
        json={"x": float(x), "y": float(y)},
    )
    assert r.status_code == 200, r.text


async def _restore_token(gm_client, char_id):
    """Move token to a benign corner (mirrors the v2.62.1 restore
    helper in test_sneak_attack_advisory.py)."""
    await _place_token(gm_client, char_id, 50.0, 50.0)


async def test_paralyzed_ally_does_not_enable_sneak_attack(
    gm_client, pip_rested, roster,
):
    """Pip attacks Krieger; the only adjacent ally (Caelan) is
    paralyzed. Per RAW the incapacitated ally doesn't count — the
    advisory should be False even though Caelan is geometrically
    5 ft from Krieger."""
    pip = pip_rested
    krieger = roster["Krieger Stonefist"]
    caelan = roster["Sir Caelan Lightbringer"]

    # Same layout as the v2.62.1 happy-path test: Caelan 5 ft from
    # Krieger; Pip 25 ft from Krieger.
    await _place_token(gm_client, pip["id"], 350.0, 350.0)
    await _place_token(gm_client, krieger["id"], 700.0, 350.0)
    await _place_token(gm_client, caelan["id"], 770.0, 350.0)

    # Caelan carries a paralyzed buff (the canonical incapacitating
    # condition; same key Hold Person installs). Pre-seeding the buff
    # via the /battle PUT is the simplest test path.
    paralyzed_buff = {
        "key": "paralyzed",
        "name": "Paralyzed (Hold Person)",
        "icon": "🥶",
        "duration_rounds": 10,
        "concentration": False,
    }
    await _seed_battle(gm_client, [
        _make_combatant(pip["name"], pip["id"]),
        _make_combatant(krieger["name"], krieger["id"],
                        hp_current=50, hp_max=75),
        _make_combatant(caelan["name"], caelan["id"],
                        buffs=[paralyzed_buff]),
    ])

    try:
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": pip["id"],
                "attack_index": 0,
                "target_combatant_id": f"tok_sa_inc_{krieger['id']}",
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        # The geometric check would return True (Caelan is 5 ft away);
        # the v2.385.0 incapacitated-skip flips it to False.
        assert data.get("sneak_attack_ally_adjacent") is False, (
            f"expected sneak_attack_ally_adjacent=False when the "
            f"adjacent ally is paralyzed; got "
            f"{data.get('sneak_attack_ally_adjacent')!r}"
        )
    finally:
        await _restore_token(gm_client, pip["id"])
        await _restore_token(gm_client, krieger["id"])
        await _restore_token(gm_client, caelan["id"])


async def test_blessed_ally_still_enables_sneak_attack(
    gm_client, pip_rested, roster,
):
    """Same setup but Caelan carries a NON-incapacitating buff
    (`bless`). Bless isn't in `_INCAPACITATING_BUFF_KEYS`, so the
    advisory should be True — only the canonical incapacitating
    conditions disqualify the adjacent-ally bonus."""
    pip = pip_rested
    krieger = roster["Krieger Stonefist"]
    caelan = roster["Sir Caelan Lightbringer"]

    await _place_token(gm_client, pip["id"], 350.0, 350.0)
    await _place_token(gm_client, krieger["id"], 700.0, 350.0)
    await _place_token(gm_client, caelan["id"], 770.0, 350.0)

    bless_buff = {
        "key": "bless",
        "name": "Bless",
        "icon": "🙏",
        "duration_rounds": 10,
        "concentration": True,
    }
    await _seed_battle(gm_client, [
        _make_combatant(pip["name"], pip["id"]),
        _make_combatant(krieger["name"], krieger["id"],
                        hp_current=50, hp_max=75),
        _make_combatant(caelan["name"], caelan["id"],
                        buffs=[bless_buff]),
    ])

    try:
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": pip["id"],
                "attack_index": 0,
                "target_combatant_id": f"tok_sa_inc_{krieger['id']}",
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        # Bless doesn't incapacitate — Caelan still counts as the
        # adjacent ally.
        assert data.get("sneak_attack_ally_adjacent") is True, (
            f"expected sneak_attack_ally_adjacent=True when the "
            f"adjacent ally carries a non-incapacitating buff "
            f"(Bless); got {data.get('sneak_attack_ally_adjacent')!r}"
        )
    finally:
        await _restore_token(gm_client, pip["id"])
        await _restore_token(gm_client, krieger["id"])
        await _restore_token(gm_client, caelan["id"])
