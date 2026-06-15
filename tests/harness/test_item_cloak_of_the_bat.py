"""v2.293.0 — advantage/disadvantage drop-in: Cloak of the Bat (RAW DMG
p.158, rare, attunement). "While wearing this cloak, you have advantage on
Dexterity (Stealth) checks."

Rides the same ``check_advantage_on`` substrate as Cloak of Elvenkind
(v2.253.0) / Boots of Elvenkind (v2.255.0) / Eyes of the Eagle (v2.254.0)
— keyed on the Stealth skill and attunement-gated. ``_roll_item_check_advantage``
reads the equipped+attuned union from ``_equipped_item_effects`` and folds
an advantage source into the PHB p.173 composition at ``/roll`` time. The
dim-light flight + polymorph-to-bat clauses are GM-narrated in v1.

Demo fixture: Magnus Shadowend (Fiend Warlock with Devil's Sight) carries
the cloak as inert spare loot (equipped=False/attuned=False) so it adds no
baseline advantage. The tests PATCH it on, roll a Stealth check, then
restore the seed inventory.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_SLUG = "cloak-of-the-bat"


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


async def _snapshot_inv(gm_client, char_id):
    data = await _sheet_json(gm_client, char_id)
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    return [dict(it) if isinstance(it, dict) else it for it in inv]


async def _patch_cloak(gm_client, char_id, *, equipped, attuned):
    """PATCH the spare cloak to a desired equipped/attuned state. Returns
    the pre-PATCH inventory snapshot for restore."""
    snapshot = await _snapshot_inv(gm_client, char_id)
    new_inv = [dict(it) if isinstance(it, dict) else it for it in snapshot]
    found = False
    for it in new_inv:
        if isinstance(it, dict) and it.get("_slug") == _SLUG:
            it["equipped"] = equipped
            it["attuned"] = attuned
            found = True
    assert found, "Magnus has no cloak-of-the-bat item"
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
async def magnus(roster):
    return next(v for k, v in roster.items() if "Magnus" in k)


async def test_cloak_grants_stealth_advantage(gm_client, magnus):
    """Equipping+attuning the cloak surfaces advantage on a Stealth roll:
    breakdown contains 2d20kh1 + roll_state_applied names the item."""
    rid = magnus["id"]
    snap = await _patch_cloak(gm_client, rid, equipped=True, attuned=True)
    try:
        await _seed_battle(gm_client, [_mkc(f"tok_bat_{rid}", rid, name="Magnus")])
        resp = await _roll_stealth(gm_client, rid)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "2d20kh1" in (data.get("breakdown") or ""), (
            f"Expected 2d20kh1; got breakdown={data.get('breakdown')!r}"
        )
        assert data.get("roll_state_applied") == (
            "auto_advantage_cloak_of_the_bat"
        ), data.get("roll_state_applied")
    finally:
        await _restore(gm_client, rid, snap)


async def test_cloak_requires_attunement(gm_client, magnus):
    """The cloak is an attunement item — equipped-but-unattuned yields no
    Stealth advantage (straight 1d20)."""
    rid = magnus["id"]
    snap = await _patch_cloak(gm_client, rid, equipped=True, attuned=False)
    try:
        await _seed_battle(gm_client, [_mkc(f"tok_bat_na_{rid}", rid, name="Magnus")])
        resp = await _roll_stealth(gm_client, rid)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "2d20kh1" not in (data.get("breakdown") or "")
        assert data.get("roll_state_applied") in (None, "")
    finally:
        await _restore(gm_client, rid, snap)


async def test_cloak_baseline_has_no_advantage(gm_client, magnus):
    """Control: with the cloak inert (seed, equipped=False), Magnus has no
    Stealth advantage — proving it's cloak-sourced."""
    rid = magnus["id"]
    await _seed_battle(gm_client, [_mkc(f"tok_bat_base_{rid}", rid, name="Magnus")])
    resp = await _roll_stealth(gm_client, rid)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "2d20kh1" not in (data.get("breakdown") or "")
    assert data.get("roll_state_applied") in (None, "")


async def test_cloak_exposes_derived_flag(gm_client, magnus):
    """The wearer's /sheet-json reports derived.check_advantage_on with
    "stealth" in skills and the cloak named in sources when attuned."""
    rid = magnus["id"]
    snap = await _patch_cloak(gm_client, rid, equipped=True, attuned=True)
    try:
        data = await _sheet_json(gm_client, rid)
        flag = (data.get("derived") or {}).get("check_advantage_on")
        assert flag is not None, (
            f"expected derived.check_advantage_on, got: {data.get('derived')!r}"
        )
        assert "stealth" in (flag.get("skills") or []), flag
        assert any(
            "Cloak of the Bat" in str(v)
            for v in (flag.get("sources") or {}).values()
        ), f"expected the cloak named in sources, got: {flag!r}"
    finally:
        await _restore(gm_client, rid, snap)
