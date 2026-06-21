"""Conjure Fey — Druid/Warlock L6, second Phase 3 CR-increase consumer.

v2.419.0 — second consumer of the summon *CR-increase* family
(`_SPELL_SUMMON_CR_MAP` + `_spell_summon_cr_for_slot()`), after Conjure
Elemental. RAW PHB p.226: a fey creature of CR 6 or lower appears; upcast
increases the challenge rating by 1 per slot level above 6th. Exactly
**one** fey is summoned and its CR climbs with the slot:

  - L6 → CR 6   (base)
  - L7 → CR 7
  - L9 → CR 9   (top of the ladder)

The endpoint gates on knowing Conjure Fey OR being a Druid / Warlock.
Caster fixtures: Mira Greenleaf (demo Druid) for the ladder; Magnus
Hexbinder (demo Warlock) for the Warlock-branch gate.

Tests:
  - L6 base → 1 fey, CR 6
  - L7 → CR 7
  - L9 → CR 9 (top of the ladder)
  - Warlock caster (Magnus) passes the class gate
  - 409 cannot_cast for a non-druid/warlock non-knower (Krieger Barbarian)
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
        "id": f"tok_cf_{c['id']}", "char_id": c["id"], "name": c["name"],
        "initiative": 10, "hp_current": 30, "hp_max": 30, "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _dismiss_all(gm_client, combatant_ids):
    for cid in combatant_ids:
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/dismiss_companion",
            json={"combatant_id": cid},
        )


async def test_conjure_fey_base_slot_cr6(gm_client, roster):
    """Mira casts at L6 base slot → exactly 1 fey at CR 6."""
    mira = roster["Mira Greenleaf"]
    await _seed_battle(gm_client, [_pc_cb(mira)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_conjure_fey",
        json={
            "character_id": mira["id"],
            "slot_level": 6,
            "x": 700.0, "y": 700.0,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    ids = [c["id"] for c in body["combatants"]]
    try:
        assert body["feature"] == "conjure-fey"
        assert body["slot_level"] == 6
        assert body["count"] == 1
        assert body["challenge_rating"] == 6
        assert len(ids) == 1
        for c in body["combatants"]:
            assert c["is_summon"] is True
            assert c["companion_key"] == "fey-spirit"
            assert c["summoned_by"] == mira["id"]
    finally:
        await _dismiss_all(gm_client, ids)


async def test_conjure_fey_l7_cr7(gm_client, roster):
    """L7 → CR 7 (+1 per slot above 6th), still exactly 1 fey."""
    mira = roster["Mira Greenleaf"]
    await _seed_battle(gm_client, [_pc_cb(mira)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_conjure_fey",
        json={
            "character_id": mira["id"],
            "slot_level": 7,
            "x": 700.0, "y": 700.0,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    ids = [c["id"] for c in body["combatants"]]
    try:
        assert body["slot_level"] == 7
        assert body["count"] == 1
        assert body["challenge_rating"] == 7
        assert len(ids) == 1
    finally:
        await _dismiss_all(gm_client, ids)


async def test_conjure_fey_l9_cr9(gm_client, roster):
    """L9 → CR 9 (top of the ladder), still exactly 1 fey."""
    mira = roster["Mira Greenleaf"]
    await _seed_battle(gm_client, [_pc_cb(mira)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_conjure_fey",
        json={
            "character_id": mira["id"],
            "slot_level": 9,
            "x": 700.0, "y": 700.0,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    ids = [c["id"] for c in body["combatants"]]
    try:
        assert body["count"] == 1
        assert body["challenge_rating"] == 9
        assert len(ids) == 1
    finally:
        await _dismiss_all(gm_client, ids)


async def test_conjure_fey_warlock_can_cast(gm_client, roster):
    """Magnus (Warlock) passes the Druid/Warlock gate → L6 = CR 6."""
    magnus = roster["Magnus Hexbinder"]
    await _seed_battle(gm_client, [_pc_cb(magnus)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_conjure_fey",
        json={
            "character_id": magnus["id"],
            "slot_level": 6,
            "x": 700.0, "y": 700.0,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    ids = [c["id"] for c in body["combatants"]]
    try:
        assert body["feature"] == "conjure-fey"
        assert body["count"] == 1
        assert body["challenge_rating"] == 6
        assert len(ids) == 1
    finally:
        await _dismiss_all(gm_client, ids)


async def test_conjure_fey_cannot_cast_non_caster(gm_client, roster):
    """Krieger (Barbarian) doesn't know the spell and isn't a Druid or
    Warlock → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _seed_battle(gm_client, [_pc_cb(krieger)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_conjure_fey",
        json={
            "character_id": krieger["id"],
            "slot_level": 6,
            "x": 700.0, "y": 700.0,
        },
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body.get("error") == "cannot_cast"
    assert "druid" in body.get("expected", "").lower()


# ─── v2.541.0 — optional catalog-creature (fey) override ──────────────


async def test_fey_catalog_creature(gm_client, roster):
    """creature_slug=dryad (Fey CR 1 ≤ the L6 cap) → one dryad with the
    catalog stat block (HP 22 / AC 11)."""
    mira = roster["Mira Greenleaf"]
    await _seed_battle(gm_client, [_pc_cb(mira)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_conjure_fey",
        json={"character_id": mira["id"], "creature_slug": "dryad",
              "x": 700.0, "y": 700.0},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    ids = [c["id"] for c in body["combatants"]]
    try:
        assert len(body["combatants"]) == 1
        c = body["combatants"][0]
        assert c["companion_key"] == "dryad"
        assert int(c["hp_max"]) == 22
        assert int(c["ac"]) == 11
    finally:
        await _dismiss_all(gm_client, ids)


async def test_fey_catalog_non_fey_400(gm_client, roster):
    """A non-fey slug (wolf — Beast) → 400."""
    mira = roster["Mira Greenleaf"]
    await _seed_battle(gm_client, [_pc_cb(mira)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_conjure_fey",
        json={"character_id": mira["id"], "creature_slug": "wolf"},
    )
    assert r.status_code == 400, r.text
