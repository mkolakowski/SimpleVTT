"""v2.255.0 — advantage/disadvantage Phase 4b drop-in: Boots of Elvenkind
(RAW DMG p.155, uncommon, NO attunement). "While you wear these boots ...
you have advantage on Dexterity (Stealth) checks that rely on moving
silently."

The no-attunement companion to Cloak of Elvenkind (v2.253.0) on the same
`check_advantage_on: ["stealth"]` substrate — the only difference is that
the boots' `_MAGIC_ITEM_PASSIVES` payload omits `requires_attunement`, so
they ride freely alongside a full 3/3 attunement loadout. No new helper or
`/roll` code — `_roll_item_check_advantage` + `_equipped_item_effects`
already generalize over the skill key and the attunement gate.

Demo fixture: Quan Reelstep (Drunken Master Monk) wears them. Quan is at
the RAW 3/3 attunement cap (Belt of Dwarvenkind + Ioun Stone of Mastery +
Mantle of Spell Resistance); the boots need no attunement, so they ride
alongside — like Mira's Ring of Swimming / Rowan's Ring of Water Walking.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_SLUG = "boots-of-elvenkind"


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
async def quan(roster):
    return roster["Quan Reelstep"]


async def test_boots_grant_stealth_advantage(gm_client, quan):
    """Quan rolls a Stealth check while wearing the boots — the /roll
    response resolves 2d20kh1 + roll_state_applied names the boots."""
    rid = quan["id"]
    await _seed_battle(gm_client, [_mkc(f"tok_boe_{rid}", rid, name="Quan")])
    resp = await _roll_stealth(gm_client, rid)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "2d20kh1" in (data.get("breakdown") or ""), (
        f"Expected 2d20kh1; got breakdown={data.get('breakdown')!r}"
    )
    assert data.get("roll_state_applied") == (
        "auto_advantage_boots_of_elvenkind"
    ), data.get("roll_state_applied")


async def test_boots_do_not_help_non_stealth_check(gm_client, quan):
    """Control: the boots grant advantage on Stealth ONLY. A Perception
    check rolls a straight 1d20 with no advantage label."""
    rid = quan["id"]
    await _seed_battle(gm_client, [_mkc(f"tok_boe_per_{rid}", rid, name="Quan")])
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


async def test_boots_advantage_cancels_with_condition_disadvantage(
    gm_client, quan,
):
    """PHB p.173: the boots' advantage + a condition's disadvantage on the
    same Stealth check cancel to a straight roll. Quan carries a Poisoned
    buff (ability-check disadvantage) on his combatant — adv + dis =
    neither, labeled canceled_*."""
    rid = quan["id"]
    await _seed_battle(gm_client, [
        _mkc(f"tok_boe_cancel_{rid}", rid, name="Quan",
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
    assert "boots_of_elvenkind" in state, state


async def test_boots_no_attunement_required(gm_client, quan):
    """The boots grant their Stealth advantage with NO attunement — Quan
    is already at the RAW 3/3 cap (Belt + Ioun + Mantle), so the only way
    the advantage fires is if the boots ride free of the attunement gate.
    The 2d20kh1 roll proves the payload has no requires_attunement."""
    rid = quan["id"]
    data = await _sheet_json(gm_client, rid)
    inv = (data.get("sheet") or {}).get("inventory") or []
    boots = next(
        (it for it in inv
         if isinstance(it, dict) and it.get("_slug") == _SLUG),
        None,
    )
    assert boots is not None, "Boots of Elvenkind not in inventory"
    assert not boots.get("attuned"), (
        "Boots should NOT be attuned — they require no attunement"
    )
    await _seed_battle(gm_client, [_mkc(f"tok_boe_noatt_{rid}", rid, name="Quan")])
    resp = await _roll_stealth(gm_client, rid)
    assert resp.status_code == 200, resp.text
    assert "2d20kh1" in (resp.json().get("breakdown") or "")


async def _set_boots_equipped(gm_client, char_id, equipped):
    data = await _sheet_json(gm_client, char_id)
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    idx = next(
        (i for i, it in enumerate(inv)
         if isinstance(it, dict) and it.get("_slug") == _SLUG),
        None,
    )
    assert idx is not None, "Boots of Elvenkind not in inventory"
    inv[idx] = {**inv[idx], "equipped": equipped}
    resp = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"inventory": inv},
    )
    assert resp.status_code == 200, resp.text


async def test_boots_unequip_drops_stealth_advantage(gm_client, quan):
    """Unequipping the boots drops the advantage — the Stealth roll reverts
    to a straight 1d20 (roll_state_applied None). Re-equips on teardown."""
    rid = quan["id"]
    await _set_boots_equipped(gm_client, rid, False)
    try:
        await _seed_battle(gm_client, [
            _mkc(f"tok_boe_unequip_{rid}", rid, name="Quan"),
        ])
        resp = await _roll_stealth(gm_client, rid)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "2d20kh1" not in (data.get("breakdown") or "")
        assert data.get("roll_state_applied") in (None, "")
    finally:
        await _set_boots_equipped(gm_client, rid, True)


async def test_boots_expose_derived_flag(gm_client, quan):
    """The wearer's /sheet-json reports derived.check_advantage_on with
    "stealth" in skills and the boots named in sources."""
    data = await _sheet_json(gm_client, quan["id"])
    flag = (data.get("derived") or {}).get("check_advantage_on")
    assert flag is not None, (
        f"expected derived.check_advantage_on, got: {data.get('derived')!r}"
    )
    assert "stealth" in (flag.get("skills") or []), flag
    assert any(
        "Boots of Elvenkind" in str(v)
        for v in (flag.get("sources") or {}).values()
    ), f"expected the boots named in sources, got: {flag!r}"
