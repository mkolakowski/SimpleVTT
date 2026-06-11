"""v2.158.97 — magic-items-automation Phase 6a: Demon Slayer Rapier
conditional rider (RAW DMG p.166). Second conditional rider after
v2.158.93's Dragon Slayer, with the same condition shape but a
``"fiend"`` predicate and 2d6 dice (vs. Dragon Slayer's "dragon"
predicate and 3d6 dice). Exercises the Phase 5c+5f substrate at
scale — no new code paths beyond the catalog row.

Demo fixture: Lyra Sunstrider (Bard) gets the Rapier at
``attack_index 3`` + ``inventory_index 7``, equipped + attuned. +1
attack/damage RAW is baked into the attack entry (+5 → +6, 1d8+2 →
1d8+3). The frighten-on-hit DC 15 WIS save (RAW) is deferred — that's
a separate save-handler hook, not a rider.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


LYRA_DEMON_SLAYER_ATTACK_IDX = 3
LYRA_DEMON_SLAYER_INV_IDX = 7


def _uplifts(data, source):
    return [u for u in (data.get("auto_uplifts") or [])
            if u.get("source") == source]


def _mkc(cid, char_id=None, name="X", creature_type="", ac=1):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": 200, "hp_max": 200,
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
async def lyra(roster):
    return roster["Lyra Sunstrider"]


async def test_demon_slayer_fires_on_fiend_target(gm_client, lyra):
    """v2.158.97 happy path. Attacking a target with
    ``creature_type: "fiend"`` surfaces a +2d6 uplift from the Demon
    Slayer Rapier. Damage type falls back to the weapon's piercing
    per RAW."""
    lyra_cid = f"tok_ds_phase6_lyra_{lyra['id']}"
    fiend_cid = "tok_ds_phase6_fiend"
    await _seed_battle(gm_client, [
        _mkc(lyra_cid, lyra["id"], name=lyra["name"]),
        _mkc(fiend_cid, None, name="Quasit", creature_type="fiend"),
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": lyra["id"],
            "attack_index": LYRA_DEMON_SLAYER_ATTACK_IDX,
            "target_combatant_id": fiend_cid,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["attack_name"] == "Demon Slayer Rapier"

    ups = _uplifts(data, "item-demon-slayer")
    assert len(ups) == 1, data.get("auto_uplifts")
    rider = ups[0]
    assert rider["label"] == "Demon Slayer"
    assert rider["expression"] == "2d6"
    assert rider["damage_type"] == "piercing"  # RAW: weapon type
    # Non-crit 2d6 → [2, 12]; crit-doubled 4d6 → [4, 24].
    assert 2 <= rider["total"] <= 24


async def test_demon_slayer_silent_on_humanoid(gm_client, lyra):
    """v2.158.97 negative case. Attacking a non-fiend target → no
    rider. The condition predicate `creature_type == "fiend"` blocks
    the uplift even with the rapier equipped + attuned."""
    lyra_cid = f"tok_ds_phase6_b_lyra_{lyra['id']}"
    bandit_cid = "tok_ds_phase6_b_bandit"
    await _seed_battle(gm_client, [
        _mkc(lyra_cid, lyra["id"], name=lyra["name"]),
        _mkc(bandit_cid, None, name="Bandit", creature_type="humanoid"),
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": lyra["id"],
            "attack_index": LYRA_DEMON_SLAYER_ATTACK_IDX,
            "target_combatant_id": bandit_cid,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    ups = _uplifts(resp.json(), "item-demon-slayer")
    assert ups == [], (
        f"Demon Slayer must not fire vs. humanoid; got {ups!r}"
    )


async def test_demon_slayer_suppressed_when_detuned(gm_client, lyra):
    """v2.158.97: detuning the Rapier suppresses the rider even on
    a fiend target. Restores attunement in teardown."""
    detune = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/attune",
        json={"inventory_index": LYRA_DEMON_SLAYER_INV_IDX,
              "attuned": False},
    )
    assert detune.status_code == 200, detune.text

    try:
        lyra_cid = f"tok_ds_phase6_c_lyra_{lyra['id']}"
        fiend_cid = "tok_ds_phase6_c_fiend"
        await _seed_battle(gm_client, [
            _mkc(lyra_cid, lyra["id"], name=lyra["name"]),
            _mkc(fiend_cid, None, name="Quasit", creature_type="fiend"),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": lyra["id"],
                "attack_index": LYRA_DEMON_SLAYER_ATTACK_IDX,
                "target_combatant_id": fiend_cid,
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        ups = _uplifts(resp.json(), "item-demon-slayer")
        assert ups == [], (
            "Detuned Demon Slayer must not fire even vs. fiends; "
            f"got {ups!r}"
        )
    finally:
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/attune",
            json={"inventory_index": LYRA_DEMON_SLAYER_INV_IDX,
                  "attuned": True},
        )
