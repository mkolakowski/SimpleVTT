"""v2.158.93 — magic-items-automation Phase 5c: Dragon Slayer Longsword
conditional rider (RAW DMG p.166). First on-hit rider whose fire
depends on the target — only fires when the target carries
``creature_type: "dragon"``.

Mechanism: `_MAGIC_ITEM_ATTACK_RIDERS["dragon-slayer"]` carries a
``condition(target_combatant) → bool`` callable. Section 6c in
`_compute_attack_auto_uplifts` invokes it after the slug + attunement
checks; if it returns falsy, the rider is skipped. Always-on riders
(Flame Tongue) omit the field and behave unchanged.

Demo fixture: Sir Caelan Lightbringer (Paladin) gets the Dragon Slayer
Longsword at attack_index 2 + inventory_index 7, equipped + attuned.
Attack entry's +1 magic bonus is baked into the bonuses/damage (per
RAW: +1 to attack/damage on top of the conditional rider).

Tests use the same battle-seed pattern as `test_attack_rider_substrate.py`:
PUT a synthetic battle with Caelan + a target combatant whose
``creature_type`` is the variable, then POST /attack with
``target_combatant_id``.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


CAELAN_DRAGON_SLAYER_ATTACK_IDX = 2
CAELAN_DRAGON_SLAYER_INV_IDX = 7


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
async def caelan(roster):
    return roster["Sir Caelan Lightbringer"]


async def test_dragon_slayer_fires_on_dragon_target(gm_client, caelan):
    """v2.158.93 happy path. Attacking a target with
    ``creature_type: "dragon"`` surfaces a +3d6 uplift from the
    Dragon Slayer Longsword. Damage type falls back to the
    weapon's slashing per RAW."""
    caelan_cid = f"tok_ds1_caelan_{caelan['id']}"
    dragon_cid = "tok_ds1_dragon"
    await _seed_battle(gm_client, [
        _mkc(caelan_cid, caelan["id"], name=caelan["name"]),
        _mkc(dragon_cid, None, name="Young Red Dragon",
             creature_type="dragon"),
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": caelan["id"],
            "attack_index": CAELAN_DRAGON_SLAYER_ATTACK_IDX,
            "target_combatant_id": dragon_cid,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["attack_name"] == "Dragon Slayer Longsword"

    ups = _uplifts(data, "item-dragon-slayer")
    assert len(ups) == 1, data.get("auto_uplifts")
    rider = ups[0]
    assert rider["label"] == "Dragon Slayer"
    assert rider["expression"] == "3d6"
    assert rider["damage_type"] == "slashing"  # falls back to weapon
    # Non-crit 3d6 → [3, 18]; crit-doubled 6d6 → [6, 36].
    assert 3 <= rider["total"] <= 36


async def test_dragon_slayer_silent_on_humanoid(gm_client, caelan):
    """v2.158.93 negative case. Attacking a non-dragon target →
    no rider. The condition predicate `creature_type == "dragon"`
    blocks the uplift even with the longsword equipped + attuned."""
    caelan_cid = f"tok_ds2_caelan_{caelan['id']}"
    bandit_cid = "tok_ds2_bandit"
    await _seed_battle(gm_client, [
        _mkc(caelan_cid, caelan["id"], name=caelan["name"]),
        _mkc(bandit_cid, None, name="Bandit", creature_type="humanoid"),
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": caelan["id"],
            "attack_index": CAELAN_DRAGON_SLAYER_ATTACK_IDX,
            "target_combatant_id": bandit_cid,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    ups = _uplifts(resp.json(), "item-dragon-slayer")
    assert ups == [], (
        f"Dragon Slayer must not fire vs. humanoid; got {ups!r}"
    )


async def test_dragon_slayer_suppressed_when_detuned(gm_client, caelan):
    """v2.158.93: detuning the Dragon Slayer suppresses the rider
    even on a dragon target. The attunement check runs before the
    condition predicate, so a detuned magic weapon is mechanically
    mundane (RAW). Restores attunement in teardown."""
    detune = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/attune",
        json={"inventory_index": CAELAN_DRAGON_SLAYER_INV_IDX,
              "attuned": False},
    )
    assert detune.status_code == 200, detune.text

    try:
        caelan_cid = f"tok_ds3_caelan_{caelan['id']}"
        dragon_cid = "tok_ds3_dragon"
        await _seed_battle(gm_client, [
            _mkc(caelan_cid, caelan["id"], name=caelan["name"]),
            _mkc(dragon_cid, None, name="Young Red Dragon",
                 creature_type="dragon"),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": caelan["id"],
                "attack_index": CAELAN_DRAGON_SLAYER_ATTACK_IDX,
                "target_combatant_id": dragon_cid,
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        ups = _uplifts(resp.json(), "item-dragon-slayer")
        assert ups == [], (
            "Detuned Dragon Slayer must not fire even vs. dragons; "
            f"got {ups!r}"
        )
    finally:
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/attune",
            json={"inventory_index": CAELAN_DRAGON_SLAYER_INV_IDX,
                  "attuned": True},
        )
