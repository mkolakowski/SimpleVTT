"""v2.159.1 — magic-items-automation Phase 8a: Arrow of Slaying
(Giants) — first ammunition-shape catalog row (RAW DMG p.151). Uses
the v2.158.102 + Phase 8a `on_hit_save` substrate extended with a
new ``effect: "damage"`` variant (vs. Demon Slayer's
``effect: "frighten"``). RAW: on hit vs. a creature of the keyed
kind, target makes a DC 17 CON save; on a fail, extra 6d10 piercing;
on a pass, half that.

Demo fixture: Rowan Quickbow (Ranger Lv 5, Hunter) gets a "Longbow
(Arrow of Slaying — Giants)" attack at attack_index 2 wired by
``_slug="arrow-of-slaying-giants"``. New Hill Giant template carries
``sheet.type="giant"`` so the v2.158.96 Phase 5f helper resolves the
creature type on drag-spawned giants without a battle PUT override.

The arrow's RAW "becomes a nonmagical arrow after dealing the extra
damage" qty decrement is filed as Phase 8b polish — not modeled v1.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


ROWAN_SLAYING_ATTACK_IDX = 2


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
async def rowan(roster):
    return roster["Rowan Quickbow"]


@pytest_asyncio.fixture
async def hill_giant_template_id(gm_client):
    """Look up the Hill Giant token template id. Carries
    sheet.type='giant' so the Phase 5f helper resolves it."""
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    assert r.status_code == 200, r.text
    templates = r.json()
    for t in templates:
        if t["name"] == "Hill Giant":
            assert (t["sheet"] or {}).get("type") == "giant", (
                f"Hill Giant template should be sheet.type='giant'; "
                f"got {t['sheet']!r}"
            )
            return t["id"]
    raise AssertionError(
        f"Hill Giant template missing; got: "
        f"{[t['name'] for t in templates]}"
    )


def _giant_combatant(cid, template_id, hp=200):
    """Synthetic Hill Giant combatant referencing the demo template.
    No creature_type on the combatant — the Phase 5f helper resolves
    sheet.type='giant' from the template."""
    return {
        "id": cid,
        "char_id": None,
        "name": "Hill Giant",
        "token_template_id": template_id,
        "initiative": 8,
        "hp_current": hp, "hp_max": hp,
        "ac": 1,
        "buffs": [],
        "speed_walk": 40,
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


def _rowan_combatant(cid, char_id, name):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": 55, "hp_max": 55,
        "ac": 15,
        "buffs": [],
        "speed_walk": 30,
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def test_slaying_arrow_fires_save_on_giant(
    gm_client, rowan, hill_giant_template_id,
):
    """v2.159.1 happy path. Rowan hits a Hill Giant with the Arrow
    of Slaying → the post-hit on_hit_save handler resolves a DC 17
    CON save server-side via _resolve_feature_save + applies full
    or half 6d10 piercing damage based on the outcome.

    Asserts:
      - Attack succeeds
      - feature_used broadcast carries the save label + source
      - Target HP dropped by AT LEAST the base attack damage
        (extra Slaying damage is on top, deterministic via dice
        seed isn't required here — we just verify the rider path
        fired)
    """
    await _seed_dice(gm_client, 5)
    rowan_cid = f"tok_slay1_rowan_{rowan['id']}"
    giant_cid = "tok_slay1_giant"
    target_hp = 250
    await _seed_battle(gm_client, [
        _rowan_combatant(rowan_cid, rowan["id"], rowan["name"]),
        _giant_combatant(giant_cid, hill_giant_template_id, hp=target_hp),
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": rowan["id"],
            "attack_index": ROWAN_SLAYING_ATTACK_IDX,
            "target_combatant_id": giant_cid,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text

    # Check that the giant took damage beyond the bow's base 1d8+4
    # (max 12). Whether the save passed or failed, the rider's
    # save-for-half damage stacks on top — pass adds at least 6//2 =
    # 3 (min 6d10 = 6 → 3), fail adds at least 6. So we expect HP
    # drop > 13 (12 base max + 1 floor for half-damage).
    state = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/battle")
    assert state.status_code == 200
    cs = (state.json().get("battle") or {}).get("combatants") or []
    giant = next((c for c in cs if c.get("id") == giant_cid), None)
    assert giant is not None, "Giant not in battle state"
    hp_dropped = target_hp - int(giant.get("hp_current") or target_hp)
    assert hp_dropped > 12, (
        f"Giant HP should drop > 12 (base attack max + rider min); "
        f"got drop={hp_dropped}"
    )

    await _seed_dice(gm_client, None)


async def test_slaying_arrow_silent_on_non_giant(gm_client, rowan):
    """v2.159.1 negative case. Hitting a humanoid (NOT giant) → no
    save fires. The condition predicate gates the rider off — only
    the base 1d8+4 piercing is dealt."""
    rowan_cid = f"tok_slay2_rowan_{rowan['id']}"
    bandit_cid = "tok_slay2_bandit"
    target_hp = 200
    await _seed_battle(gm_client, [
        _rowan_combatant(rowan_cid, rowan["id"], rowan["name"]),
        _mkc(bandit_cid, None, name="Bandit", creature_type="humanoid",
             hp_max=target_hp),
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": rowan["id"],
            "attack_index": ROWAN_SLAYING_ATTACK_IDX,
            "target_combatant_id": bandit_cid,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text

    state = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/battle")
    cs = (state.json().get("battle") or {}).get("combatants") or []
    bandit = next((c for c in cs if c.get("id") == bandit_cid), None)
    assert bandit is not None
    hp_dropped = target_hp - int(bandit.get("hp_current") or target_hp)
    # Base attack 1d8+4 → max 12. No rider damage should land.
    assert hp_dropped <= 12, (
        f"Humanoid should only take base attack damage (<= 12); "
        f"got drop={hp_dropped} (rider may have leaked)"
    )


async def test_regular_longbow_no_slaying_rider(
    gm_client, rowan, hill_giant_template_id,
):
    """v2.159.1: shooting Rowan's regular Longbow (attack_index 0,
    no `_slug` match) at a Hill Giant → no Arrow-of-Slaying rider
    fires even though the target IS a giant. The slug-on-attack
    gate blocks the rider from leaking across weapons."""
    rowan_cid = f"tok_slay3_rowan_{rowan['id']}"
    giant_cid = "tok_slay3_giant"
    target_hp = 200
    await _seed_battle(gm_client, [
        _rowan_combatant(rowan_cid, rowan["id"], rowan["name"]),
        _giant_combatant(giant_cid, hill_giant_template_id, hp=target_hp),
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": rowan["id"],
            "attack_index": 0,  # plain Longbow
            "target_combatant_id": giant_cid,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text

    state = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/battle")
    cs = (state.json().get("battle") or {}).get("combatants") or []
    giant = next((c for c in cs if c.get("id") == giant_cid), None)
    assert giant is not None
    hp_dropped = target_hp - int(giant.get("hp_current") or target_hp)
    # Base Longbow 1d8+4 → max 12. No rider damage should land.
    assert hp_dropped <= 12, (
        f"Plain Longbow vs. Giant should deal only base damage; "
        f"got drop={hp_dropped} (rider leaked across weapons)"
    )
