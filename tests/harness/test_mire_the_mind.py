"""v2.99.137 — Mire the Mind (Warlock invocation) tests.

RAW (PHB p.111): "Prerequisite: 5th level. You can cast Slow once
using a warlock spell slot. You can't do so again until you finish
a long rest."

v2.99.137 extends /cast_slow to accept class_slug="warlock" +
optional via_invocation="mire-the-mind" body flag. When present,
the endpoint:
  - Validates the invocation is on the caster's feats
  - Gates on the `mire-the-mind-uses` 1/long-rest resource
  - Skips the standard "Slow on spell list" check (Slow isn't a
    Warlock spell — the invocation grants it)
  - Decrements both the spell slot AND the Mire the Mind resource

Magnus has the invocation + resource on his seed as of v2.99.137.

Tests:
  - happy path: Magnus casts Slow via Mire the Mind → buff installs
    + Mire the Mind use decrements
  - second cast same long rest → 409 not_enough_uses
  - warlock without via_invocation flag → 409 missing_invocation
  - krieger (non-Warlock) with class_slug=warlock → wrong_class
    (gated before the invocation check)
  - reset via long rest restores the Mire the Mind use
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _mkc(cid, char_id=None, name="X", speed_walk=30):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": 50, "hp_max": 50,
        "speed_walk": speed_walk,
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False,
                    "movement": 0, "dash_bonus_ft": 0},
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


@pytest_asyncio.fixture
async def magnus_rested(gm_client, roster):
    """Long-rest Magnus so Mire the Mind use is fresh."""
    magnus = roster["Magnus Hexbinder"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )
    return magnus


async def test_mire_the_mind_cast_slow_happy_path(
    gm_client, magnus_rested, roster,
):
    """Magnus casts Slow via Mire the Mind → 200 + buff installs."""
    magnus = magnus_rested
    krieger = roster["Krieger Stonefist"]
    mg_tok = f"tok_mtm_mg_{magnus['id']}"
    kr_tok = f"tok_mtm_kr_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(mg_tok, magnus["id"], name=magnus["name"]),
        _mkc(kr_tok, krieger["id"], name=krieger["name"], speed_walk=40),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_slow",
        json={
            "character_id": magnus["id"],
            "class_slug": "warlock",
            "via_invocation": "mire-the-mind",
            "slot_level": 3,
            "target_combatant_ids": [kr_tok],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    affected = data.get("affected") or []
    assert len(affected) == 1
    assert affected[0]["installed"] is True


async def test_mire_the_mind_warlock_without_flag_409(
    gm_client, magnus_rested, roster,
):
    """class_slug=warlock without via_invocation → 409
    missing_invocation (Slow isn't a Warlock spell).
    """
    magnus = magnus_rested
    krieger = roster["Krieger Stonefist"]
    mg_tok = f"tok_mtm_no_inv_mg_{magnus['id']}"
    kr_tok = f"tok_mtm_no_inv_kr_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(mg_tok, magnus["id"], name=magnus["name"]),
        _mkc(kr_tok, krieger["id"], name=krieger["name"], speed_walk=40),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_slow",
        json={
            "character_id": magnus["id"],
            "class_slug": "warlock",
            "slot_level": 3,
            "target_combatant_ids": [kr_tok],
            "override": True,
        },
    )
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert data.get("error") == "missing_invocation"


async def test_mire_the_mind_second_cast_409_not_enough_uses(
    gm_client, magnus_rested, roster,
):
    """Cast twice without resting between → second call 409
    not_enough_uses (1/long rest gate).
    """
    magnus = magnus_rested
    krieger = roster["Krieger Stonefist"]
    mg_tok = f"tok_mtm_2x_mg_{magnus['id']}"
    kr_tok = f"tok_mtm_2x_kr_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(mg_tok, magnus["id"], name=magnus["name"]),
        _mkc(kr_tok, krieger["id"], name=krieger["name"], speed_walk=40),
    ])
    cast1 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_slow",
        json={
            "character_id": magnus["id"],
            "class_slug": "warlock",
            "via_invocation": "mire-the-mind",
            "slot_level": 3,
            "target_combatant_ids": [kr_tok],
            "override": True,
        },
    )
    assert cast1.status_code == 200, cast1.text
    # Second cast — same long rest, should 409.
    cast2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_slow",
        json={
            "character_id": magnus["id"],
            "class_slug": "warlock",
            "via_invocation": "mire-the-mind",
            "slot_level": 3,
            "target_combatant_ids": [kr_tok],
            "override": True,
        },
    )
    assert cast2.status_code == 409, cast2.text
    data = cast2.json()
    assert data.get("error") == "not_enough_uses"
    assert data.get("resource_key") == "mire-the-mind-uses"


async def test_mire_the_mind_rejects_non_warlock(gm_client, roster):
    """Krieger (Barbarian) with class_slug=warlock → wrong_class
    fires from the standard class-membership check (Krieger isn't
    a Warlock).
    """
    krieger = roster["Krieger Stonefist"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_slow",
        json={
            "character_id": krieger["id"],
            "class_slug": "warlock",
            "via_invocation": "mire-the-mind",
            "slot_level": 3,
            "target_combatant_ids": ["x"],
            "override": True,
        },
    )
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert data.get("error") == "wrong_class"
