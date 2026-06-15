"""v2.339.0 — magic-items: Dwarven Thrower (RAW DMG p.166, very rare,
attunement by a dwarf). The first rider to use the new `bonus_dice_vs`
field: an unconditional base `dice: "1d8"` bludgeoning rider (fires on
every hit, Frost Brand shape) PLUS an extra `1d8` vs a giant. RAW: a
ranged hit deals +1d8, or +2d8 vs a giant (= base 1d8 + bonus 1d8).

The base rider surfaces in `auto_uplifts` with `source:
"item-dwarven-thrower"`; the giant bonus with `source:
"item-dwarven-thrower-bonus"`. Both gated on the wielder having the
hammer equipped + attuned (RAW attunement). Demo fixture: Brother Tavik
Stonebrow (Hill Dwarf Cleric — the dwarf-only attunement is RAW-legal)
carries it at `attack_index 3`, seeded inert (PATCH-in-test).

Tests:
  - vs giant (Hill Giant template): base +1d8 AND giant +1d8 bonus fire.
  - vs humanoid: base +1d8 only — no giant bonus.
  - detuned: neither rider fires (attunement gate).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


TAVIK_DWARVEN_THROWER_ATTACK_IDX = 3
_DWARVEN_THROWER_SLUG = "dwarven-thrower"


def _uplifts(data, source):
    return [u for u in (data.get("auto_uplifts") or [])
            if u.get("source") == source]


def _mkc(cid, char_id=None, name="X", creature_type="", token_template_id=None,
        ac=1, hp_max=200):
    c = {
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
    if token_template_id is not None:
        c["token_template_id"] = token_template_id
    return c


async def _seed_battle(gm_client, combatants):
    return await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


async def _snapshot_inv(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    inv = list((resp.json().get("sheet") or {}).get("inventory") or [])
    return [dict(it) if isinstance(it, dict) else it for it in inv]


async def _patch_inv(gm_client, char_id, slug, *, equipped, attuned):
    snapshot = await _snapshot_inv(gm_client, char_id)
    new_inv = [dict(it) if isinstance(it, dict) else it for it in snapshot]
    found = False
    for it in new_inv:
        if isinstance(it, dict) and it.get("_slug") == slug:
            it["equipped"] = equipped
            it["attuned"] = attuned
            found = True
    assert found, f"Tavik has no {slug} item"
    resp = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"inventory": new_inv},
    )
    assert resp.status_code == 200, resp.text
    return snapshot


async def _restore_inv(gm_client, char_id, snapshot):
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"inventory": snapshot},
    )


async def _hill_giant_template_id(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    assert r.status_code == 200, r.text
    giant = next((t for t in r.json() if t.get("name") == "Hill Giant"), None)
    assert giant is not None, "Hill Giant template missing from the demo seed"
    return giant["id"]


@pytest_asyncio.fixture
async def tavik(roster):
    return roster["Brother Tavik Stonebrow"]


async def _attack(gm_client, tavik, target_cid):
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": tavik["id"],
            "attack_index": TAVIK_DWARVEN_THROWER_ATTACK_IDX,
            "target_combatant_id": target_cid,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_dwarven_thrower_base_and_giant_bonus(gm_client, tavik):
    """v2.339.0 happy path #1. Vs a Hill Giant, BOTH the unconditional base
    +1d8 AND the giant +1d8 bonus fire (RAW +2d8 total vs giants)."""
    template_id = await _hill_giant_template_id(gm_client)
    snap = await _patch_inv(
        gm_client, tavik["id"], _DWARVEN_THROWER_SLUG,
        equipped=True, attuned=True,
    )
    try:
        tavik_cid = f"tok_dt_giant_tavik_{tavik['id']}"
        giant_cid = "tok_dt_giant_target"
        await _seed_battle(gm_client, [
            _mkc(tavik_cid, tavik["id"], name=tavik["name"]),
            _mkc(giant_cid, None, name="Hill Giant", creature_type="giant",
                 token_template_id=template_id, hp_max=105),
        ])
        data = await _attack(gm_client, tavik, giant_cid)
        assert data["attack_name"] == "Dwarven Thrower (thrown)"

        base = _uplifts(data, "item-dwarven-thrower")
        assert len(base) == 1, data.get("auto_uplifts")
        assert base[0]["expression"] == "1d8"
        assert base[0]["damage_type"] == "bludgeoning"

        bonus = _uplifts(data, "item-dwarven-thrower-bonus")
        assert len(bonus) == 1, (
            f"Giant bonus +1d8 should fire vs a giant; got "
            f"{data.get('auto_uplifts')}"
        )
        assert bonus[0]["expression"] == "1d8"
        assert bonus[0]["damage_type"] == "bludgeoning"
    finally:
        await _restore_inv(gm_client, tavik["id"], snap)


async def test_dwarven_thrower_base_only_vs_humanoid(gm_client, tavik):
    """v2.339.0 negative case. Vs a humanoid, only the unconditional base
    +1d8 fires — the giant bonus is suppressed by the creature-type gate."""
    snap = await _patch_inv(
        gm_client, tavik["id"], _DWARVEN_THROWER_SLUG,
        equipped=True, attuned=True,
    )
    try:
        tavik_cid = f"tok_dt_hum_tavik_{tavik['id']}"
        bandit_cid = "tok_dt_hum_target"
        await _seed_battle(gm_client, [
            _mkc(tavik_cid, tavik["id"], name=tavik["name"]),
            _mkc(bandit_cid, None, name="Bandit", creature_type="humanoid",
                 hp_max=60),
        ])
        data = await _attack(gm_client, tavik, bandit_cid)
        base = _uplifts(data, "item-dwarven-thrower")
        assert len(base) == 1, data.get("auto_uplifts")
        assert base[0]["expression"] == "1d8"
        bonus = _uplifts(data, "item-dwarven-thrower-bonus")
        assert bonus == [], (
            f"Giant bonus must NOT fire vs. humanoid; got {bonus!r}"
        )
    finally:
        await _restore_inv(gm_client, tavik["id"], snap)


async def test_dwarven_thrower_suppressed_when_detuned(gm_client, tavik):
    """v2.339.0: detuned (equipped but not attuned) → neither the base nor
    the giant-bonus rider fires (RAW attunement gate)."""
    template_id = await _hill_giant_template_id(gm_client)
    snap = await _patch_inv(
        gm_client, tavik["id"], _DWARVEN_THROWER_SLUG,
        equipped=True, attuned=False,
    )
    try:
        tavik_cid = f"tok_dt_det_tavik_{tavik['id']}"
        giant_cid = "tok_dt_det_target"
        await _seed_battle(gm_client, [
            _mkc(tavik_cid, tavik["id"], name=tavik["name"]),
            _mkc(giant_cid, None, name="Hill Giant", creature_type="giant",
                 token_template_id=template_id, hp_max=105),
        ])
        data = await _attack(gm_client, tavik, giant_cid)
        assert _uplifts(data, "item-dwarven-thrower") == [], (
            "Base rider must not fire when detuned."
        )
        assert _uplifts(data, "item-dwarven-thrower-bonus") == [], (
            "Giant bonus must not fire when detuned."
        )
    finally:
        await _restore_inv(gm_client, tavik["id"], snap)
