"""v2.296.0 — Rod of Alertness (RAW DMG p.193, very rare, attunement): while
holding the rod you have advantage on Wisdom (Perception) checks and on
initiative rolls; it also casts four detect/see-invisibility spells and can be
planted to make a +1 AC/saves protective aura.

The headline testable benefit — advantage on Perception checks — rides the
v2.253.0 ``check_advantage_on`` substrate (Cloak/Boots of Elvenkind, Eyes of
the Eagle/Minute Seeing, Cloak of the Bat, Robe of Eyes), keyed on the
Perception skill and attunement-gated. ``_roll_item_check_advantage`` reads the
equipped+attuned union from ``_equipped_item_effects`` and folds an advantage
source into the PHB p.173 composition at ``/roll`` time. The initiative-roll
advantage, the rod's spells, and the planted protective aura are GM-narrated in
v1.

Demo fixture: Garrik Ironside (Fighter) carries the rod as inert spare loot
(equipped=False/attuned=False) — he has no other perception-advantage item, so
the inert baseline cleanly proves the rod is the source. The tests PATCH it on,
roll a Perception check, then restore the seed inventory.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_SLUG = "rod-of-alertness"


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


async def _snapshot_inv(gm_client, char_id):
    data = await _sheet_json(gm_client, char_id)
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    return [dict(it) if isinstance(it, dict) else it for it in inv]


async def _patch_rod(gm_client, char_id, *, equipped, attuned):
    snapshot = await _snapshot_inv(gm_client, char_id)
    new_inv = [dict(it) if isinstance(it, dict) else it for it in snapshot]
    found = False
    for it in new_inv:
        if isinstance(it, dict) and it.get("_slug") == _SLUG:
            it["equipped"] = equipped
            it["attuned"] = attuned
            found = True
    assert found, "Garrik has no rod-of-alertness item"
    resp = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"inventory": new_inv},
    )
    assert resp.status_code == 200, resp.text
    return snapshot


async def _restore(gm_client, char_id, snapshot):
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"inventory": snapshot},
    )


@pytest_asyncio.fixture
async def garrik(roster):
    return next(v for k, v in roster.items() if "Garrik" in k)


async def test_rod_grants_perception_advantage(gm_client, garrik):
    """Equipping+attuning the rod surfaces advantage on a Perception roll:
    breakdown contains 2d20kh1 + roll_state_applied names the item."""
    rid = garrik["id"]
    snap = await _patch_rod(gm_client, rid, equipped=True, attuned=True)
    try:
        await _seed_battle(gm_client, [_mkc(f"tok_rod_{rid}", rid, name="Garrik")])
        resp = await _roll_perception(gm_client, rid)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "2d20kh1" in (data.get("breakdown") or ""), (
            f"Expected 2d20kh1; got breakdown={data.get('breakdown')!r}"
        )
        assert data.get("roll_state_applied") == (
            "auto_advantage_rod_of_alertness"
        ), data.get("roll_state_applied")
    finally:
        await _restore(gm_client, rid, snap)


async def test_rod_requires_attunement(gm_client, garrik):
    """The rod is an attunement item — equipped-but-unattuned yields no
    Perception advantage (straight 1d20)."""
    rid = garrik["id"]
    snap = await _patch_rod(gm_client, rid, equipped=True, attuned=False)
    try:
        await _seed_battle(gm_client, [_mkc(f"tok_rod_na_{rid}", rid, name="Garrik")])
        resp = await _roll_perception(gm_client, rid)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "2d20kh1" not in (data.get("breakdown") or "")
        assert data.get("roll_state_applied") in (None, "")
    finally:
        await _restore(gm_client, rid, snap)


async def test_rod_baseline_has_no_advantage(gm_client, garrik):
    """Control: with the rod inert (seed, equipped=False), Garrik has no
    Perception advantage — proving it's rod-sourced."""
    rid = garrik["id"]
    await _seed_battle(gm_client, [_mkc(f"tok_rod_base_{rid}", rid, name="Garrik")])
    resp = await _roll_perception(gm_client, rid)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "2d20kh1" not in (data.get("breakdown") or "")
    assert data.get("roll_state_applied") in (None, "")


async def test_rod_exposes_derived_flag(gm_client, garrik):
    """The wearer's /sheet-json reports derived.check_advantage_on with
    "perception" in skills and the rod named in sources when attuned."""
    rid = garrik["id"]
    snap = await _patch_rod(gm_client, rid, equipped=True, attuned=True)
    try:
        data = await _sheet_json(gm_client, rid)
        flag = (data.get("derived") or {}).get("check_advantage_on")
        assert flag is not None, (
            f"expected derived.check_advantage_on, got: {data.get('derived')!r}"
        )
        assert "perception" in (flag.get("skills") or []), flag
        assert any(
            "Rod of Alertness" in str(v)
            for v in (flag.get("sources") or {}).values()
        ), f"expected the rod named in sources, got: {flag!r}"
    finally:
        await _restore(gm_client, rid, snap)
