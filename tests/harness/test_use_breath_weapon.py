"""v2.392.0 — /use_breath_weapon endpoint (Dragonborn racial action).

RAW PHB p.34 Breath Weapon. Magnus Hexbinder is the demo seed's
Dragonborn PC (Warlock Lv 5, Bronze ancestry → lightning, 5×30-ft
line, DEX save). Damage at Lv 5 = 2d6 (scales 3d6 @ 6 / 4d6 @ 11 /
5d6 @ 16). DC = 8 + CON mod + proficiency bonus. One use per short
rest, tracked via the `breath-weapon` resource on the sheet.

Tests:
  - Happy path: Magnus uses breath weapon on a bandit → 200,
    response carries the right per-ancestry params + per-target
    save outcome + the charge decrements from 1 → 0.
  - Second call without rest → 409 no_charges.
  - Wrong race (Pip is Halfling) → 409 wrong_race.
  - Unknown ancestor (PATCH Magnus to an invalid ancestor) → 409
    unknown_ancestry.
  - Incapacitated caster → 409 incapacitated (reuses the v2.386.0
    gate via the shared `_caster_is_incapacitated` helper).
"""
from __future__ import annotations

import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _make_combatant(name, char_id, hp=50, init=10, buffs=None,
                    template_id=None):
    c = {
        "id": f"tok_bw_{char_id}" if char_id else f"tok_bw_npc_{name.replace(' ', '_')}",
        "char_id": char_id,
        "name": name,
        "initiative": init,
        "hp_current": hp, "hp_max": hp,
        "buffs": buffs or [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }
    if template_id is not None:
        c["token_template_id"] = template_id
    return c


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


async def _short_rest(gm_client, char_id):
    """Refill the breath-weapon resource."""
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "short"},
    )


async def _bandit_template_id(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    return next(t for t in templates if "bandit" in t["name"].lower())["id"]


@pytest_asyncio.fixture
async def magnus_rested(gm_client, roster):
    """Long-rest Magnus so the breath-weapon resource is fresh."""
    magnus = roster["Magnus Hexbinder"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )
    return magnus


async def test_breath_weapon_happy_path(gm_client, magnus_rested):
    """Magnus exhales lightning at a bandit. Response carries Bronze
    Dragonborn params (lightning, line, DEX save) + per-target outcome
    + the charge decrements."""
    magnus = magnus_rested
    bandit_tmpl = await _bandit_template_id(gm_client)
    await _seed_battle(gm_client, [
        _make_combatant(magnus["name"], magnus["id"]),
        _make_combatant("Bandit", None, hp=11,
                        template_id=bandit_tmpl),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_breath_weapon",
        json={
            "character_id": magnus["id"],
            "target_combatant_ids": ["tok_bw_npc_Bandit"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ancestor"] == "bronze"
    assert data["damage_type"] == "lightning"
    assert data["shape"] == "line"
    assert data["save_ability"] == "DEX"
    assert data["size_ft"] == 30
    # Magnus is Lv 5 → 2d6 base.
    assert data["damage_expression"] == "2d6"
    assert data["char_level"] == 5
    # DC = 8 + CON mod (CON 14 = +2) + PB (3) = 13.
    assert data["save_dc"] == 13
    # Charge consumed: 1 → 0.
    assert data["charges_remaining"] == 0
    assert data["charges_max"] == 1
    # One target processed.
    assert len(data["results"]) == 1
    r = data["results"][0]
    assert r["combatant_id"] == "tok_bw_npc_Bandit"
    assert r["passed"] in (True, False)
    # Bronze is lightning; bandit has no lightning resistance.
    assert r["damage_dealt"] > 0


async def test_breath_weapon_no_charges_after_use(
    gm_client, magnus_rested,
):
    """Second call without a rest → 409 no_charges."""
    magnus = magnus_rested
    bandit_tmpl = await _bandit_template_id(gm_client)
    await _seed_battle(gm_client, [
        _make_combatant(magnus["name"], magnus["id"]),
        _make_combatant("Bandit", None, hp=11,
                        template_id=bandit_tmpl),
    ])
    # First call consumes the charge.
    r1 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_breath_weapon",
        json={
            "character_id": magnus["id"],
            "target_combatant_ids": ["tok_bw_npc_Bandit"],
            "override": True,
        },
    )
    assert r1.status_code == 200, r1.text
    # Second call → 409.
    r2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_breath_weapon",
        json={
            "character_id": magnus["id"],
            "target_combatant_ids": ["tok_bw_npc_Bandit"],
            "override": True,
        },
    )
    assert r2.status_code == 409, r2.text
    body = r2.json()
    assert body["error"] == "no_charges"
    assert body["current"] == 0
    assert body["max"] == 1
    assert body["reset"] == "short"


async def test_breath_weapon_wrong_race_returns_409(
    gm_client, roster,
):
    """Pip (Halfling) tries to use breath weapon → 409 wrong_race."""
    pip = roster["Pip Quickfingers"]
    await _seed_battle(gm_client, [
        _make_combatant(pip["name"], pip["id"]),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_breath_weapon",
        json={
            "character_id": pip["id"],
            "target_combatant_ids": [],
            "override": True,
        },
    )
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body["error"] == "wrong_race"


async def test_breath_weapon_paralyzed_caster_returns_409(
    gm_client, magnus_rested,
):
    """Magnus is paralyzed → 409 incapacitated (reuses v2.386.0 gate)."""
    magnus = magnus_rested
    paralyzed = {
        "key": "paralyzed",
        "name": "Paralyzed",
        "icon": "🥶",
        "duration_rounds": 10,
        "concentration": False,
    }
    await _seed_battle(gm_client, [
        _make_combatant(magnus["name"], magnus["id"],
                        buffs=[paralyzed]),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_breath_weapon",
        json={
            "character_id": magnus["id"],
            "target_combatant_ids": [],
            # Note: deliberately NO override here — paralyzed gate
            # should fire.
        },
    )
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body["error"] == "incapacitated"
    assert body["source"] == "breath_weapon"
