"""v2.253.0 — advantage/disadvantage Phase 4b: Cloak of Elvenkind
(RAW DMG p.158, uncommon, attunement). "while you wear this cloak with
its hood up ... you have advantage on Dexterity (Stealth) checks made to
hide."

This is the first ITEM-granted *check* advantage source (Phase 4a's
Cloak of Displacement was the first item *attack* disadvantage). The
Phase 2b condition substrate reads adv/dis from combatant buffs at
``/roll`` time; the cloak is a passive on the wearer's CHARACTER SHEET,
so ``_roll_item_check_advantage`` reads ``_equipped_item_effects``'s new
``check_advantage_on`` union (attunement-gated) and folds an advantage
source into the existing PHB p.173 composition. The skill gate means
only a Stealth check fires — a Perception roll is untouched. Cancel
logic (PHB p.173) — advantage + any disadvantage source = straight roll
— comes for free.

Demo fixture: Rowan Quickbow (Ranger) wears it as a (4th) attuned item —
the seed predates the strict 3/3 cap, which lives only on the /attune
runtime endpoint (Cloak of Displacement / Lyra precedent, v2.252.0).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_SLUG = "cloak-of-elvenkind"


def _mkc(cid, char_id=None, name="X", buffs=None):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": 40, "hp_max": 40,
        "buffs": buffs or [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _seed_battle(gm_client, combatants):
    return await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _roll_stealth(gm_client, char_id, stat_key="stealth"):
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20",
            "character_id": char_id,
            "stat_key": stat_key,
            "stat_ability": "DEX",
        },
    )


@pytest_asyncio.fixture
async def rowan(roster):
    return roster["Rowan Quickbow"]


async def test_cloak_grants_stealth_advantage(gm_client, rowan):
    """Rowan rolls a Stealth check while wearing the attuned cloak —
    the /roll response resolves 2d20kh1 + roll_state_applied names the
    cloak."""
    rid = rowan["id"]
    await _seed_battle(gm_client, [_mkc(f"tok_coe_{rid}", rid, name="Rowan")])
    resp = await _roll_stealth(gm_client, rid)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "2d20kh1" in (data.get("breakdown") or ""), (
        f"Expected 2d20kh1; got breakdown={data.get('breakdown')!r}"
    )
    assert data.get("roll_state_applied") == (
        "auto_advantage_cloak_of_elvenkind"
    ), data.get("roll_state_applied")


async def test_cloak_does_not_help_non_stealth_check(gm_client, rowan):
    """Control: the cloak grants advantage on Stealth ONLY. A Perception
    check rolls a straight 1d20 with no advantage label."""
    rid = rowan["id"]
    await _seed_battle(gm_client, [_mkc(f"tok_coe_per_{rid}", rid, name="Rowan")])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20",
            "character_id": rid,
            "stat_key": "perception",
            "stat_ability": "WIS",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "2d20kh1" not in (data.get("breakdown") or "")
    assert data.get("roll_state_applied") in (None, "")


async def test_cloak_advantage_cancels_with_condition_disadvantage(
    gm_client, rowan,
):
    """PHB p.173: the cloak's advantage + a condition's disadvantage on
    the same Stealth check cancel to a straight roll. Rowan carries a
    Poisoned buff (ability-check disadvantage) on his combatant — adv +
    dis = neither, labeled canceled_*."""
    rid = rowan["id"]
    await _seed_battle(gm_client, [
        _mkc(f"tok_coe_cancel_{rid}", rid, name="Rowan",
             buffs=[{"key": "poisoned", "name": "Poisoned"}]),
    ])
    resp = await _roll_stealth(gm_client, rid)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "2d20" not in (data.get("breakdown") or ""), (
        f"Cancel should leave a single 1d20; got {data.get('breakdown')!r}"
    )
    state = data.get("roll_state_applied") or ""
    assert state.startswith("canceled_"), state
    assert "cloak_of_elvenkind" in state, state


async def _set_cloak_attuned(gm_client, char_id, attuned):
    """Flip the cloak's `attuned` flag via a sheet-fields PATCH rather
    than /attune. The cloak is Rowan's 4th attuned item (the demo seed
    predates the RAW 3/3 cap, which lives only on the /attune endpoint),
    so re-attuning via /attune would 409 on the cap. The PATCH path
    mirrors the seed-load bypass and exercises the walker's attunement
    gate directly — which is exactly what this test asserts on."""
    data = await _sheet_json(gm_client, char_id)
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    idx = next(
        (i for i, it in enumerate(inv)
         if isinstance(it, dict) and it.get("_slug") == _SLUG),
        None,
    )
    assert idx is not None, "Cloak of Elvenkind not in inventory"
    inv[idx] = {**inv[idx], "attuned": attuned}
    resp = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"inventory": inv},
    )
    assert resp.status_code == 200, resp.text


async def test_cloak_detuned_drops_stealth_advantage(gm_client, rowan):
    """Detuning the cloak drops the advantage — the Stealth roll reverts
    to a straight 1d20 (roll_state_applied None). Restores attunement in
    teardown via PATCH (cap-independent)."""
    rid = rowan["id"]
    await _set_cloak_attuned(gm_client, rid, False)
    try:
        await _seed_battle(gm_client, [
            _mkc(f"tok_coe_detune_{rid}", rid, name="Rowan"),
        ])
        resp = await _roll_stealth(gm_client, rid)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "2d20kh1" not in (data.get("breakdown") or "")
        assert data.get("roll_state_applied") in (None, "")
    finally:
        await _set_cloak_attuned(gm_client, rid, True)


async def test_cloak_exposes_derived_flag(gm_client, rowan):
    """The wearer's /sheet-json reports derived.check_advantage_on with
    "stealth" in skills and the cloak named in sources."""
    data = await _sheet_json(gm_client, rowan["id"])
    flag = (data.get("derived") or {}).get("check_advantage_on")
    assert flag is not None, (
        f"expected derived.check_advantage_on, got: {data.get('derived')!r}"
    )
    assert "stealth" in (flag.get("skills") or []), flag
    assert any(
        "Cloak of Elvenkind" in str(v)
        for v in (flag.get("sources") or {}).values()
    ), f"expected the cloak named in sources, got: {flag!r}"
