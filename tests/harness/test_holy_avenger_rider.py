"""v2.322.0 — magic-items: Holy Avenger (RAW DMG p.174, legendary,
attunement, "any sword"). Pure substrate clone of the v2.319.0 Mace of
Disruption rider — same multi-type conditional (fiend OR undead), but
with `dice: "2d10"` (vs. 2d6 on the Mace) per RAW. Same
`_compute_attack_auto_uplifts` block 6c machinery — zero new engine
code. The +3 attack/damage half is baked into the wielder's seeded
attack row (Vorpal/Dragon Slayer precedent for magic +X swords); the
save-advantage aura is GM-narrated in v1.

Demo fixture: Sir Caelan Lightbringer (Devotion Paladin) carries a Holy
Avenger Longsword at `attack_index 3` + inventory tail, seeded INERT
(equipped=False, attuned=False). Tests PATCH the inventory
equipped+attuned via /sheet-fields (which bypasses the /attune 3-item
cap, since Caelan is at 3 seed-attuned: Ioun Reserve + Ring of Feather
Falling + Armor of Resistance), run the rider assertion, then restore.

Tests:
  - Fires vs fiend (creature_type == "fiend") → `item-holy-avenger`
    uplift, +2d10 radiant.
  - Fires vs undead (creature_type == "undead") → same uplift, +2d10
    radiant.
  - Silent vs humanoid (no creature_type match) → no uplift.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


CAELAN_HOLY_AVENGER_ATTACK_IDX = 3
_HOLY_AVENGER_SLUG = "holy-avenger"


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
    snapshot = await _snapshot_inv(gm_client, char_id)
    new_inv = [dict(it) if isinstance(it, dict) else it for it in snapshot]
    found = False
    for it in new_inv:
        if isinstance(it, dict) and it.get("_slug") == slug:
            it["equipped"] = equipped
            it["attuned"] = attuned
            found = True
    assert found, f"Caelan has no {slug} item"
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
async def caelan(roster):
    return roster["Sir Caelan Lightbringer"]


async def test_holy_avenger_fires_on_fiend_target(gm_client, caelan):
    """v2.322.0 happy path #1. Attacking a target with creature_type='fiend'
    surfaces the +2d10 radiant uplift from the Holy Avenger. Exercises the
    first slot in the predicate's two-type list."""
    snap = await _patch_inv(
        gm_client, caelan["id"], _HOLY_AVENGER_SLUG,
        equipped=True, attuned=True,
    )
    try:
        caelan_cid = f"tok_avenger_fiend_caelan_{caelan['id']}"
        quasit_cid = "tok_avenger_fiend_quasit"
        await _seed_battle(gm_client, [
            _mkc(caelan_cid, caelan["id"], name=caelan["name"]),
            _mkc(quasit_cid, None, name="Quasit", creature_type="fiend"),
        ])

        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": caelan["id"],
                "attack_index": CAELAN_HOLY_AVENGER_ATTACK_IDX,
                "target_combatant_id": quasit_cid,
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["attack_name"] == "Holy Avenger Longsword"

        ups = _uplifts(data, "item-holy-avenger")
        assert len(ups) == 1, data.get("auto_uplifts")
        rider = ups[0]
        assert rider["label"] == "Holy Avenger"
        assert rider["expression"] == "2d10"
        assert rider["damage_type"] == "radiant"
        # Non-crit 2d10 → [2, 20]; crit-doubled 4d10 → [4, 40].
        assert 2 <= rider["total"] <= 40
    finally:
        await _restore_inv(gm_client, caelan["id"], snap)


async def test_holy_avenger_fires_on_undead_target(gm_client, caelan):
    """v2.322.0 happy path #2. Same shape vs. undead — proves the lambda's
    `in (...)` membership check, not a single-type equality."""
    snap = await _patch_inv(
        gm_client, caelan["id"], _HOLY_AVENGER_SLUG,
        equipped=True, attuned=True,
    )
    try:
        caelan_cid = f"tok_avenger_undead_caelan_{caelan['id']}"
        skel_cid = "tok_avenger_undead_skel"
        await _seed_battle(gm_client, [
            _mkc(caelan_cid, caelan["id"], name=caelan["name"]),
            _mkc(skel_cid, None, name="Skeleton", creature_type="undead"),
        ])

        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": caelan["id"],
                "attack_index": CAELAN_HOLY_AVENGER_ATTACK_IDX,
                "target_combatant_id": skel_cid,
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        ups = _uplifts(data, "item-holy-avenger")
        assert len(ups) == 1, data.get("auto_uplifts")
        rider = ups[0]
        assert rider["expression"] == "2d10"
        assert rider["damage_type"] == "radiant"
        assert 2 <= rider["total"] <= 40
    finally:
        await _restore_inv(gm_client, caelan["id"], snap)


async def test_holy_avenger_silent_on_humanoid(gm_client, caelan):
    """v2.322.0 negative case. Attacking a non-fiend/non-undead target → no
    rider. The condition predicate `creature_type in ("fiend", "undead")`
    blocks the uplift on humanoid targets like a Bandit."""
    snap = await _patch_inv(
        gm_client, caelan["id"], _HOLY_AVENGER_SLUG,
        equipped=True, attuned=True,
    )
    try:
        caelan_cid = f"tok_avenger_humanoid_caelan_{caelan['id']}"
        bandit_cid = "tok_avenger_humanoid_bandit"
        await _seed_battle(gm_client, [
            _mkc(caelan_cid, caelan["id"], name=caelan["name"]),
            _mkc(bandit_cid, None, name="Bandit", creature_type="humanoid"),
        ])

        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": caelan["id"],
                "attack_index": CAELAN_HOLY_AVENGER_ATTACK_IDX,
                "target_combatant_id": bandit_cid,
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        ups = _uplifts(resp.json(), "item-holy-avenger")
        assert ups == [], (
            f"Holy Avenger must not fire vs. humanoid; got {ups!r}"
        )
    finally:
        await _restore_inv(gm_client, caelan["id"], snap)
