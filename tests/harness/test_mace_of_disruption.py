"""v2.319.0 — magic-items: Mace of Disruption (RAW DMG p.179, rare,
attunement). Sun Blade-shape conditional rider (the v2.158.93 Dragon
Slayer / v2.158.104 Sun Blade `dice + condition` substrate) but with TWO
creature types in the predicate (fiend OR undead) instead of one. RAW:
"when you hit a fiend or an undead with this magic weapon, that creature
takes an extra 2d6 radiant damage."

Demo fixture: Brother Tavik Stonebrow (Life Cleric Lv 8) carries the mace
as inert spare loot at `attack_index 2` + inventory tail (equipped=False,
attuned=False). Tests PATCH the inventory equipped+attuned via
/sheet-fields (which bypasses the /attune 3-item cap — Tavik is already at
4 seed-attuned), run the rider assertion, then restore on teardown.
Follows the v2.318.1 Sword of Life Stealing spare-loot pattern.

The "destroy if target HP ≤ 25" + fear-save-on-pass RAW clauses don't
compose cleanly on the generalized rider substrate and are GM-narrated
in v1.

Tests:
  - Fires vs fiend (creature_type == "fiend") → `item-mace-of-disruption`
    uplift, +2d6 radiant.
  - Fires vs undead (creature_type == "undead") → same uplift, +2d6 radiant.
  - Silent vs humanoid (no creature_type match) → no uplift.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


TAVIK_MACE_ATTACK_IDX = 2
_MACE_SLUG = "mace-of-disruption"


def _uplifts(data, source):
    return [u for u in (data.get("auto_uplifts") or [])
            if u.get("source") == source]


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


async def _snapshot_inv(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    return [dict(it) if isinstance(it, dict) else it for it in inv]


async def _patch_inv(gm_client, char_id, slug, *, equipped, attuned):
    """PATCH the inventory item with `_slug == slug` to the given equip /
    attune state via /sheet-fields (bypasses the /attune cap). Returns
    the original snapshot for teardown restore."""
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


@pytest_asyncio.fixture
async def tavik(roster):
    return roster["Brother Tavik Stonebrow"]


async def test_mace_fires_on_fiend_target(gm_client, tavik):
    """v2.319.0 happy path #1. Attacking a target with creature_type='fiend'
    surfaces the +2d6 radiant uplift from the Mace of Disruption. Exercises
    the first slot in the predicate's two-type list."""
    snap = await _patch_inv(
        gm_client, tavik["id"], _MACE_SLUG, equipped=True, attuned=True,
    )
    try:
        tavik_cid = f"tok_mace_fiend_tavik_{tavik['id']}"
        quasit_cid = "tok_mace_fiend_quasit"
        await _seed_battle(gm_client, [
            _mkc(tavik_cid, tavik["id"], name=tavik["name"]),
            _mkc(quasit_cid, None, name="Quasit", creature_type="fiend"),
        ])

        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": tavik["id"],
                "attack_index": TAVIK_MACE_ATTACK_IDX,
                "target_combatant_id": quasit_cid,
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["attack_name"] == "Mace of Disruption"

        ups = _uplifts(data, "item-mace-of-disruption")
        assert len(ups) == 1, data.get("auto_uplifts")
        rider = ups[0]
        assert rider["label"] == "Mace of Disruption"
        assert rider["expression"] == "2d6"
        assert rider["damage_type"] == "radiant"
        # Non-crit 2d6 → [2, 12]; crit-doubled 4d6 → [4, 24].
        assert 2 <= rider["total"] <= 24
    finally:
        await _restore_inv(gm_client, tavik["id"], snap)


async def test_mace_fires_on_undead_target(gm_client, tavik):
    """v2.319.0 happy path #2. Attacking a target with creature_type='undead'
    surfaces the same +2d6 radiant uplift. Exercises the second slot in the
    predicate's two-type list — proves the lambda's `in (...)` membership
    check, not a single-type equality."""
    snap = await _patch_inv(
        gm_client, tavik["id"], _MACE_SLUG, equipped=True, attuned=True,
    )
    try:
        tavik_cid = f"tok_mace_undead_tavik_{tavik['id']}"
        skel_cid = "tok_mace_undead_skel"
        await _seed_battle(gm_client, [
            _mkc(tavik_cid, tavik["id"], name=tavik["name"]),
            _mkc(skel_cid, None, name="Skeleton", creature_type="undead"),
        ])

        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": tavik["id"],
                "attack_index": TAVIK_MACE_ATTACK_IDX,
                "target_combatant_id": skel_cid,
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        ups = _uplifts(data, "item-mace-of-disruption")
        assert len(ups) == 1, data.get("auto_uplifts")
        rider = ups[0]
        assert rider["expression"] == "2d6"
        assert rider["damage_type"] == "radiant"
        assert 2 <= rider["total"] <= 24
    finally:
        await _restore_inv(gm_client, tavik["id"], snap)


async def test_mace_silent_on_humanoid(gm_client, tavik):
    """v2.319.0 negative case. Attacking a non-fiend/non-undead target → no
    rider. The condition predicate `creature_type in ("fiend", "undead")`
    blocks the uplift on humanoid targets like a Bandit."""
    snap = await _patch_inv(
        gm_client, tavik["id"], _MACE_SLUG, equipped=True, attuned=True,
    )
    try:
        tavik_cid = f"tok_mace_humanoid_tavik_{tavik['id']}"
        bandit_cid = "tok_mace_humanoid_bandit"
        await _seed_battle(gm_client, [
            _mkc(tavik_cid, tavik["id"], name=tavik["name"]),
            _mkc(bandit_cid, None, name="Bandit", creature_type="humanoid"),
        ])

        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": tavik["id"],
                "attack_index": TAVIK_MACE_ATTACK_IDX,
                "target_combatant_id": bandit_cid,
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        ups = _uplifts(resp.json(), "item-mace-of-disruption")
        assert ups == [], (
            f"Mace of Disruption must not fire vs. humanoid; got {ups!r}"
        )
    finally:
        await _restore_inv(gm_client, tavik["id"], snap)
