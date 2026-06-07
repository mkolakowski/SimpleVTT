"""Conjure Animals — Druid/Ranger L3, the first multi-summon retrofit.

v2.99.443 — Phase 7.2 of docs/plans/movement-and-summons.md. Builds on
the summon primitive in a loop: `/cast_conjure_animals` stands up `count`
beast combatants (wolves), each on its own grid cell, via repeated
`_summon_companion` calls. Gates on knowing Conjure Animals OR being a
Druid / Ranger.

Caster fixture: Mira Greenleaf (demo Druid).

Tests:
  - 8 wolves: the default conjures 8 distinct summon combatants + 8
    tokens, all `summoned_by` the caster, at spaced x positions.
  - count clamp: count 2 → exactly 2.
  - 409 cannot_cast: Krieger (Barbarian).
"""
from .conftest import CAMPAIGN_ID


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": False},
    )


def _pc_cb(c):
    return {
        "id": f"tok_test_{c['id']}", "char_id": c["id"], "name": c["name"],
        "initiative": 10, "hp_current": 30, "hp_max": 30, "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _tokens(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")
    return r.json()["tokens"]


async def _dismiss_all(gm_client, combatant_ids):
    for cid in combatant_ids:
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/dismiss_companion",
            json={"combatant_id": cid},
        )


async def test_conjure_animals_eight_wolves(gm_client, roster):
    """Mira conjures the default 8 wolves → 8 distinct summon combatants +
    8 tokens, all owned by Mira, at spaced x positions."""
    mira = roster["Mira Greenleaf"]
    await _seed_battle(gm_client, [_pc_cb(mira)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_conjure_animals",
        json={"character_id": mira["id"], "x": 700.0, "y": 700.0,
              "spacing": 70},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    combatants = body["combatants"]
    ids = [c["id"] for c in combatants]
    try:
        assert body["feature"] == "conjure-animals"
        assert body["count"] == 8
        assert len(combatants) == 8
        assert len(set(ids)) == 8  # all distinct
        assert len(body["token_ids"]) == 8
        for c in combatants:
            assert c["is_summon"] is True
            assert c["companion_key"] == "wolf"
            assert c["summoned_by"] == mira["id"]

        toks = {t["id"]: t for t in await _tokens(gm_client)}
        xs = []
        for tid in body["token_ids"]:
            assert tid in toks
            xs.append(toks[tid]["x"])
        # Spaced 70 px apart starting at x=700.
        assert xs == [700.0 + 70 * i for i in range(8)]
    finally:
        await _dismiss_all(gm_client, ids)


async def test_conjure_animals_count_clamp(gm_client, roster):
    """count=2 → exactly two wolves."""
    mira = roster["Mira Greenleaf"]
    await _seed_battle(gm_client, [_pc_cb(mira)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_conjure_animals",
        json={"character_id": mira["id"], "count": 2, "x": 700.0, "y": 700.0},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    ids = [c["id"] for c in body["combatants"]]
    try:
        assert body["count"] == 2
        assert len(ids) == 2
    finally:
        await _dismiss_all(gm_client, ids)


async def test_conjure_animals_cannot_cast(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_conjure_animals",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "cannot_cast"
