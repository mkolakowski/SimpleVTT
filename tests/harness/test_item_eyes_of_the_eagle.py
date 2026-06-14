"""v2.254.0 — advantage/disadvantage Phase 4b drop-in: Eyes of the Eagle
(RAW DMG p.166, uncommon, attunement). "While wearing these crystal
lenses, you have advantage on Wisdom (Perception) checks that rely on
sight."

Rides the same ``check_advantage_on`` substrate landed in v2.253.0
(Cloak of Elvenkind) — only the skill key differs (``perception`` vs.
``stealth``). ``_roll_item_check_advantage`` reads the attunement-gated
union from ``_equipped_item_effects`` and folds an advantage source into
the PHB p.173 composition at ``/roll`` time. The skill gate means only a
Perception check fires — a Stealth roll is untouched. Cancel logic (adv
+ any disadvantage source = straight roll) comes for free.

Demo fixture: Mira Greenleaf (Druid, Perception-proficient, WIS 17)
wears it as a (4th) attuned item — the seed predates the strict 3/3 cap,
which lives only on the /attune runtime endpoint (Cloak of Elvenkind /
Rowan precedent, v2.253.0).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_SLUG = "eyes-of-the-eagle"


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


async def _roll_perception(gm_client, char_id, stat_key="perception"):
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20",
            "character_id": char_id,
            "stat_key": stat_key,
            "stat_ability": "WIS",
        },
    )


@pytest_asyncio.fixture
async def mira(roster):
    return roster["Mira Greenleaf"]


async def test_eyes_grant_perception_advantage(gm_client, mira):
    """Mira rolls a Perception check while wearing the attuned lenses —
    the /roll response resolves 2d20kh1 + roll_state_applied names the
    item."""
    rid = mira["id"]
    await _seed_battle(gm_client, [_mkc(f"tok_eye_{rid}", rid, name="Mira")])
    resp = await _roll_perception(gm_client, rid)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "2d20kh1" in (data.get("breakdown") or ""), (
        f"Expected 2d20kh1; got breakdown={data.get('breakdown')!r}"
    )
    assert data.get("roll_state_applied") == (
        "auto_advantage_eyes_of_the_eagle"
    ), data.get("roll_state_applied")


async def test_eyes_do_not_help_non_perception_check(gm_client, mira):
    """Control: the lenses grant advantage on Perception ONLY. A Stealth
    check rolls a straight 1d20 with no advantage label."""
    rid = mira["id"]
    await _seed_battle(gm_client, [_mkc(f"tok_eye_st_{rid}", rid, name="Mira")])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20",
            "character_id": rid,
            "stat_key": "stealth",
            "stat_ability": "DEX",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "2d20kh1" not in (data.get("breakdown") or "")
    assert data.get("roll_state_applied") in (None, "")


async def test_eyes_advantage_cancels_with_condition_disadvantage(
    gm_client, mira,
):
    """PHB p.173: the lenses' advantage + a condition's disadvantage on
    the same Perception check cancel to a straight roll. Mira carries a
    Poisoned buff (ability-check disadvantage) on her combatant — adv +
    dis = neither, labeled canceled_*."""
    rid = mira["id"]
    await _seed_battle(gm_client, [
        _mkc(f"tok_eye_cancel_{rid}", rid, name="Mira",
             buffs=[{"key": "poisoned", "name": "Poisoned"}]),
    ])
    resp = await _roll_perception(gm_client, rid)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "2d20" not in (data.get("breakdown") or ""), (
        f"Cancel should leave a single 1d20; got {data.get('breakdown')!r}"
    )
    state = data.get("roll_state_applied") or ""
    assert state.startswith("canceled_"), state
    assert "eyes_of_the_eagle" in state, state


async def _set_eyes_attuned(gm_client, char_id, attuned):
    """Flip the lenses' `attuned` flag via a sheet-fields PATCH rather
    than /attune. The lenses are Mira's 4th attuned item (the demo seed
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
    assert idx is not None, "Eyes of the Eagle not in inventory"
    inv[idx] = {**inv[idx], "attuned": attuned}
    resp = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"inventory": inv},
    )
    assert resp.status_code == 200, resp.text


async def test_eyes_detuned_drop_perception_advantage(gm_client, mira):
    """Detuning the lenses drops the advantage — the Perception roll
    reverts to a straight 1d20 (roll_state_applied None). Restores
    attunement in teardown via PATCH (cap-independent)."""
    rid = mira["id"]
    await _set_eyes_attuned(gm_client, rid, False)
    try:
        await _seed_battle(gm_client, [
            _mkc(f"tok_eye_detune_{rid}", rid, name="Mira"),
        ])
        resp = await _roll_perception(gm_client, rid)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "2d20kh1" not in (data.get("breakdown") or "")
        assert data.get("roll_state_applied") in (None, "")
    finally:
        await _set_eyes_attuned(gm_client, rid, True)


async def test_eyes_expose_derived_flag(gm_client, mira):
    """The wearer's /sheet-json reports derived.check_advantage_on with
    "perception" in skills and the lenses named in sources."""
    data = await _sheet_json(gm_client, mira["id"])
    flag = (data.get("derived") or {}).get("check_advantage_on")
    assert flag is not None, (
        f"expected derived.check_advantage_on, got: {data.get('derived')!r}"
    )
    assert "perception" in (flag.get("skills") or []), flag
    assert any(
        "Eyes of the Eagle" in str(v)
        for v in (flag.get("sources") or {}).values()
    ), f"expected the lenses named in sources, got: {flag!r}"
