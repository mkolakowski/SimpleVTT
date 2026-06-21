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


async def test_conjure_animals_base_slot_multiplier_one(gm_client, roster):
    """v2.414.0 — an explicit base-slot (L3) cast keeps the ×1
    multiplier: base_count 2 → 2 wolves, multiplier 1."""
    mira = roster["Mira Greenleaf"]
    await _seed_battle(gm_client, [_pc_cb(mira)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_conjure_animals",
        json={"character_id": mira["id"], "count": 2, "slot_level": 3,
              "x": 700.0, "y": 700.0},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    ids = [c["id"] for c in body["combatants"]]
    try:
        assert body["base_count"] == 2
        assert body["multiplier"] == 1
        assert body["slot_level"] == 3
        assert body["count"] == 2
        assert len(ids) == 2
    finally:
        await _dismiss_all(gm_client, ids)


async def test_conjure_animals_l5_doubles(gm_client, roster):
    """v2.414.0 — a 5th-level slot doubles the count: base_count 2 ×2 →
    4 wolves."""
    mira = roster["Mira Greenleaf"]
    await _seed_battle(gm_client, [_pc_cb(mira)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_conjure_animals",
        json={"character_id": mira["id"], "count": 2, "slot_level": 5,
              "x": 700.0, "y": 700.0},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    ids = [c["id"] for c in body["combatants"]]
    try:
        assert body["base_count"] == 2
        assert body["multiplier"] == 2
        assert body["count"] == 4
        assert len(ids) == 4
    finally:
        await _dismiss_all(gm_client, ids)


async def test_conjure_animals_l7_triples(gm_client, roster):
    """v2.414.0 — a 7th-level slot triples the count: base_count 2 ×3 →
    6 wolves."""
    mira = roster["Mira Greenleaf"]
    await _seed_battle(gm_client, [_pc_cb(mira)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_conjure_animals",
        json={"character_id": mira["id"], "count": 2, "slot_level": 7,
              "x": 700.0, "y": 700.0},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    ids = [c["id"] for c in body["combatants"]]
    try:
        assert body["multiplier"] == 3
        assert body["count"] == 6
        assert len(ids) == 6
    finally:
        await _dismiss_all(gm_client, ids)


async def test_conjure_animals_l9_quadruples(gm_client, roster):
    """v2.414.0 — a 9th-level slot quadruples the count: base_count 1 ×4
    → 4 wolves (the single CR-2 option, scaled)."""
    mira = roster["Mira Greenleaf"]
    await _seed_battle(gm_client, [_pc_cb(mira)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_conjure_animals",
        json={"character_id": mira["id"], "count": 1, "slot_level": 9,
              "x": 700.0, "y": 700.0},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    ids = [c["id"] for c in body["combatants"]]
    try:
        assert body["base_count"] == 1
        assert body["multiplier"] == 4
        assert body["count"] == 4
        assert len(ids) == 4
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


# ─── v2.539.0 — optional catalog-creature override ────────────────────


async def test_conjure_animals_catalog_beast(gm_client, roster):
    """beast_slug=giant-spider, count=2 (CR1 ≤ the CR-1 tier) → two
    spiders with the catalog stat block (HP 26 / AC 14), tracked under
    companion_key 'giant-spider'."""
    mira = roster["Mira Greenleaf"]
    await _seed_battle(gm_client, [_pc_cb(mira)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_conjure_animals",
        json={"character_id": mira["id"], "count": 2,
              "beast_slug": "giant-spider", "x": 700.0, "y": 700.0},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    ids = [c["id"] for c in body["combatants"]]
    try:
        assert body["count"] == 2
        assert len(body["combatants"]) == 2
        for c in body["combatants"]:
            assert c["companion_key"] == "giant-spider"
            assert c["is_summon"] is True
            assert int(c["hp_max"]) == 26
            assert int(c["ac"]) == 14
    finally:
        await _dismiss_all(gm_client, ids)


async def test_conjure_animals_catalog_cr_too_high_400(gm_client, roster):
    """beast_slug=black-bear (CR ½) with count=8 (the ¼ tier) → 400."""
    mira = roster["Mira Greenleaf"]
    await _seed_battle(gm_client, [_pc_cb(mira)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_conjure_animals",
        json={"character_id": mira["id"], "count": 8,
              "beast_slug": "black-bear"},
    )
    assert r.status_code == 400, r.text


async def test_conjure_animals_catalog_non_beast_400(gm_client, roster):
    """beast_slug=goblin (Humanoid) → 400."""
    mira = roster["Mira Greenleaf"]
    await _seed_battle(gm_client, [_pc_cb(mira)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_conjure_animals",
        json={"character_id": mira["id"], "count": 1, "beast_slug": "goblin"},
    )
    assert r.status_code == 400, r.text


async def test_conjure_animals_catalog_unknown_slug_400(gm_client, roster):
    """An unknown beast_slug → 400."""
    mira = roster["Mira Greenleaf"]
    await _seed_battle(gm_client, [_pc_cb(mira)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_conjure_animals",
        json={"character_id": mira["id"], "count": 1,
              "beast_slug": "no-such-beast-xyz"},
    )
    assert r.status_code == 400, r.text
