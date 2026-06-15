"""v2.320.0 — magic-items: Vicious Weapon (RAW DMG p.209, rare, NO
attunement). First `on_nat_20` item to (a) require no attunement (the
substrate skips the equipped/attuned check for `requires_attunement:
False` items — slug match alone is sufficient) and (b) omit `damage_type`
from its catalog row so the dispatcher's fallback picks up the wielding
weapon's own damage type. RAW: "When you roll a 20 on your attack roll
with this magic weapon, your critical hit deals an extra 2d6 damage of
the weapon's type."

Demo fixture: Krieger Stonefist (Half-Orc Barbarian) carries a Vicious
Greataxe at `attack_index 2` + inventory tail, equipped (no attunement).
Stacks compositionally with his Half-Orc Savage Attacks (+1 weapon die
on crit) for a savage nat-20 burst.

Tests:
  - Happy path: nat 20 on the Vicious Greataxe → +2d6 broadcast with
    `damage_type: "slashing"` (the FALLBACK from the attack row, not
    declared on the catalog row).
  - Slug-gate: nat 20 on Krieger's vanilla Greataxe (attack_index 0,
    no `_slug`) → no Vicious broadcast (slug mismatch).
  - Damage-type-fallback contract is verified inside the happy path
    via the broadcast's `damage_type` field.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


KRIEGER_VICIOUS_ATTACK_IDX = 2
KRIEGER_VANILLA_GREATAXE_IDX = 0


async def _seed_dice(gm_client, seed):
    r = await gm_client.post(
        "/api/test/dice/seed", json={"seed": seed},
    )
    assert r.status_code == 200, r.text


def _mkc(cid, char_id=None, name="X", creature_type="humanoid", ac=1,
        hp_max=200):
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
async def krieger(roster):
    return roster["Krieger Stonefist"]


async def test_vicious_nat_20_extra_damage(gm_client, gm_ws, krieger):
    """v2.320.0 happy path. With a seeded RNG that lands d20=20 on
    Krieger's Vicious Greataxe attack, the Vicious Weapon post-hit handler
    rolls +2d6 via the on_nat_20 effect="damage" branch and broadcasts a
    feature_used with source='item-vicious-weapon-nat20'. The broadcast's
    `damage_type` field is "slashing" — the fallback from the attack row,
    NOT declared on the catalog row.

    Iterates seeds 0..199 finding one that lands d20=20 on the first swing.
    """
    target_hp_max = 200
    nat_20_seed = None
    for seed in range(0, 200):
        await _seed_dice(gm_client, seed)
        krieger_cid = f"tok_vicious_krieger_{krieger['id']}_{seed}"
        target_cid = f"tok_vicious_target_{seed}"
        await _seed_battle(gm_client, [
            _mkc(krieger_cid, krieger["id"], name=krieger["name"]),
            _mkc(target_cid, None, name="Bandit", hp_max=target_hp_max),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": krieger["id"],
                "attack_index": KRIEGER_VICIOUS_ATTACK_IDX,
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
        "Krieger's first Vicious Greataxe swing."
    )

    vicious_msgs = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source")
        == "item-vicious-weapon-nat20"
    ]
    assert vicious_msgs, (
        f"Nat 20 landed on seed {nat_20_seed} but no Vicious Weapon "
        f"broadcast. Sources seen: "
        f"{[(m.get('data') or {}).get('source') for m in gm_ws.buffered('feature_used')]}"
    )
    msg_data = vicious_msgs[-1].get("data") or {}
    assert "Vicious Weapon" in (msg_data.get("feature_name") or "")
    # v2.320.1 — `damage_type` is a top-level field on the broadcast (no
    # longer only in `feature_desc` prose). Catalog row omits `damage_type`,
    # so the dispatcher falls back to the attack's own damage type
    # ("slashing" for the Greataxe).
    assert msg_data.get("damage_type") == "slashing", (
        f"Vicious Weapon damage_type must fall through to weapon "
        f"(slashing); got {msg_data.get('damage_type')!r}"
    )
    # 2d6 → [2, 12]. Not crit-doubled (post-hit rider rolls its own dice).
    hp_dealt = int(msg_data.get("hp_dealt") or 0)
    assert 2 <= hp_dealt <= 12, (
        f"Vicious 2d6 damage out of [2, 12]: got {hp_dealt}"
    )

    await _seed_dice(gm_client, None)


async def test_vicious_slug_gate_blocks_vanilla_greataxe(gm_client, gm_ws, krieger):
    """v2.320.0 negative case. Krieger's vanilla Greataxe (attack_index 0)
    carries no `_slug` field, so even on a natural 20 the Vicious Weapon
    rider must NOT fire. Proves the substrate's slug gate, not just the
    nat-20 gate."""
    nat_20_seed = None
    for seed in range(0, 200):
        await _seed_dice(gm_client, seed)
        krieger_cid = f"tok_vanilla_krieger_{krieger['id']}_{seed}"
        target_cid = f"tok_vanilla_target_{seed}"
        await _seed_battle(gm_client, [
            _mkc(krieger_cid, krieger["id"], name=krieger["name"]),
            _mkc(target_cid, None, name="Bandit"),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": krieger["id"],
                "attack_index": KRIEGER_VANILLA_GREATAXE_IDX,
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
        "Krieger's vanilla Greataxe swing."
    )

    # Vicious rider must NOT have fired on the vanilla Greataxe (no _slug).
    vicious_msgs = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source")
        == "item-vicious-weapon-nat20"
    ]
    assert not vicious_msgs, (
        f"Nat 20 on the vanilla Greataxe at seed {nat_20_seed} should NOT "
        f"fire the Vicious Weapon rider (slug gate). Got: "
        f"{[(m.get('data') or {}).get('source') for m in gm_ws.buffered('feature_used')]}"
    )

    await _seed_dice(gm_client, None)


async def test_vicious_no_attunement_required(gm_client, krieger):
    """v2.320.0: the substrate documents `requires_attunement: False` — so
    the wielder doesn't need an `attuned: True` flag on the inventory item.
    This test smokes that the seed item exposes the expected fields and
    doesn't carry an `attuned` flag (matching the no-attunement RAW)."""
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    inv = (resp.json().get("sheet") or {}).get("inventory") or []
    vicious = next(
        (it for it in inv
         if isinstance(it, dict) and it.get("_slug") == "vicious-weapon"),
        None,
    )
    assert vicious is not None, (
        "Krieger should carry a vicious-weapon item; got slugs="
        f"{[(it.get('_slug') if isinstance(it, dict) else None) for it in inv]}"
    )
    assert vicious.get("equipped") is True, vicious
    # `attuned` should be absent or False; never True (RAW: no attunement).
    assert not vicious.get("attuned"), (
        f"Vicious Greataxe must not carry attuned=True (RAW no "
        f"attunement); got {vicious!r}"
    )
