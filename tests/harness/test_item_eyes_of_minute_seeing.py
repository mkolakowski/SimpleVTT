"""v2.292.0 — advantage/disadvantage drop-in: Eyes of Minute Seeing (RAW
DMG p.166, uncommon, NO attunement). "While wearing these crystal lenses,
you have advantage on Intelligence (Investigation) checks that rely on
sight while searching an area or studying an object within 1 foot of you."

Rides the same ``check_advantage_on`` substrate landed in v2.253.0 (Cloak
of Elvenkind) / v2.254.0 (Eyes of the Eagle) — only the skill key differs
(``investigation``). The no-attunement companion to Eyes of the Eagle, so
the seed is equipped (no ``attuned`` flag) following the Boots of Elvenkind
precedent. ``_roll_item_check_advantage`` reads the equipped union from
``_equipped_item_effects`` and folds an advantage source into the PHB p.173
composition at ``/roll`` time. The skill gate means only an Investigation
check fires — a non-Investigation roll is untouched. Cancel logic (adv +
any disadvantage source = straight roll) comes for free.

Demo fixture: Pip Quickfingers (Rogue) wears the lenses equipped alongside
her full 3/3 attunement loadout — no-attunement items don't consume a slot.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_SLUG = "eyes-of-minute-seeing"


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


async def _roll_investigation(gm_client, char_id, stat_key="investigation"):
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20",
            "character_id": char_id,
            "stat_key": stat_key,
            "stat_ability": "INT",
        },
    )


@pytest_asyncio.fixture
async def pip(roster):
    return next(v for k, v in roster.items() if "Pip" in k)


async def test_eyes_grant_investigation_advantage(gm_client, pip):
    """Pip rolls an Investigation check while wearing the lenses — the
    /roll response resolves 2d20kh1 + roll_state_applied names the item."""
    rid = pip["id"]
    await _seed_battle(gm_client, [_mkc(f"tok_min_{rid}", rid, name="Pip")])
    resp = await _roll_investigation(gm_client, rid)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "2d20kh1" in (data.get("breakdown") or ""), (
        f"Expected 2d20kh1; got breakdown={data.get('breakdown')!r}"
    )
    assert data.get("roll_state_applied") == (
        "auto_advantage_eyes_of_minute_seeing"
    ), data.get("roll_state_applied")


async def test_eyes_do_not_help_non_investigation_check(gm_client, pip):
    """Control: the lenses grant advantage on Investigation ONLY. A
    Perception check rolls a straight 1d20 with no advantage label."""
    rid = pip["id"]
    await _seed_battle(gm_client, [_mkc(f"tok_min_pc_{rid}", rid, name="Pip")])
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


async def test_eyes_advantage_cancels_with_condition_disadvantage(
    gm_client, pip,
):
    """PHB p.173: the lenses' advantage + a condition's disadvantage on
    the same Investigation check cancel to a straight roll. Pip carries a
    Poisoned buff (ability-check disadvantage) on her combatant — adv +
    dis = neither, labeled canceled_*."""
    rid = pip["id"]
    await _seed_battle(gm_client, [
        _mkc(f"tok_min_cancel_{rid}", rid, name="Pip",
             buffs=[{"key": "poisoned", "name": "Poisoned"}]),
    ])
    resp = await _roll_investigation(gm_client, rid)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "2d20" not in (data.get("breakdown") or ""), (
        f"Cancel should leave a single 1d20; got {data.get('breakdown')!r}"
    )
    state = data.get("roll_state_applied") or ""
    assert state.startswith("canceled_"), state
    assert "eyes_of_minute_seeing" in state, state


async def test_eyes_expose_derived_flag(gm_client, pip):
    """The wearer's /sheet-json reports derived.check_advantage_on with
    "investigation" in skills and the lenses named in sources."""
    data = await _sheet_json(gm_client, pip["id"])
    flag = (data.get("derived") or {}).get("check_advantage_on")
    assert flag is not None, (
        f"expected derived.check_advantage_on, got: {data.get('derived')!r}"
    )
    assert "investigation" in (flag.get("skills") or []), flag
    assert any(
        "Eyes of Minute Seeing" in str(v)
        for v in (flag.get("sources") or {}).values()
    ), f"expected the lenses named in sources, got: {flag!r}"
