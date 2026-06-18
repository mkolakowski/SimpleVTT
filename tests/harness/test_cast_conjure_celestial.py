"""Conjure Celestial — Cleric L7, Phase 3 CR-increase tier-walk consumer.

v2.420.0 — third (and final) consumer of the summon *CR-increase* family,
and the one that needed a non-linear helper. RAW PHB p.225: a celestial
of CR 4 or lower appears; "when you cast this spell using a 9th-level
spell slot, you summon a celestial of CR 5 or lower." Unlike Conjure
Elemental / Fey (which climb +1 CR per slot via the linear helper), the
CR jumps in a step — CR 4 at L7/L8, CR 5 only at L9 — so the endpoint
reads the tier-walk substrate (`_SPELL_SUMMON_CR_TIER_MAP` via
`_spell_summon_cr_tier_for_slot()`). Exactly one celestial is summoned.

  - L7 → CR 4   (base)
  - L8 → CR 4   (same tier)
  - L9 → CR 5   (top tier)

The endpoint gates on knowing Conjure Celestial OR being a Cleric.
Caster fixture: Brother Tavik Stonebrow (demo Cleric) for the ladder.

Tests:
  - L7 base → 1 celestial, CR 4
  - L8 → CR 4 (same tier, not yet bumped)
  - L9 → CR 5 (top tier)
  - 409 cannot_cast for a non-cleric non-knower (Krieger Barbarian)
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
        "id": f"tok_cc_{c['id']}", "char_id": c["id"], "name": c["name"],
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


async def test_conjure_celestial_base_slot_cr4(gm_client, roster):
    """Tavik casts at L7 base slot → exactly 1 celestial at CR 4."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _seed_battle(gm_client, [_pc_cb(tavik)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_conjure_celestial",
        json={
            "character_id": tavik["id"],
            "slot_level": 7,
            "x": 700.0, "y": 700.0,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    ids = [c["id"] for c in body["combatants"]]
    try:
        assert body["feature"] == "conjure-celestial"
        assert body["slot_level"] == 7
        assert body["count"] == 1
        assert body["challenge_rating"] == 4
        assert len(ids) == 1
        for c in body["combatants"]:
            assert c["is_summon"] is True
            assert c["companion_key"] == "celestial-spirit"
            assert c["summoned_by"] == tavik["id"]
    finally:
        await _dismiss_all(gm_client, ids)


async def test_conjure_celestial_l8_still_cr4(gm_client, roster):
    """L8 → still CR 4 (same tier; the bump only lands at L9)."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _seed_battle(gm_client, [_pc_cb(tavik)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_conjure_celestial",
        json={
            "character_id": tavik["id"],
            "slot_level": 8,
            "x": 700.0, "y": 700.0,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    ids = [c["id"] for c in body["combatants"]]
    try:
        assert body["slot_level"] == 8
        assert body["count"] == 1
        assert body["challenge_rating"] == 4
        assert len(ids) == 1
    finally:
        await _dismiss_all(gm_client, ids)


async def test_conjure_celestial_l9_cr5(gm_client, roster):
    """L9 → CR 5 (the top tier), still exactly 1 celestial."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _seed_battle(gm_client, [_pc_cb(tavik)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_conjure_celestial",
        json={
            "character_id": tavik["id"],
            "slot_level": 9,
            "x": 700.0, "y": 700.0,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    ids = [c["id"] for c in body["combatants"]]
    try:
        assert body["count"] == 1
        assert body["challenge_rating"] == 5
        assert len(ids) == 1
    finally:
        await _dismiss_all(gm_client, ids)


async def test_conjure_celestial_cannot_cast_non_caster(gm_client, roster):
    """Krieger (Barbarian) doesn't know the spell and isn't a Cleric →
    409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _seed_battle(gm_client, [_pc_cb(krieger)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_conjure_celestial",
        json={
            "character_id": krieger["id"],
            "slot_level": 7,
            "x": 700.0, "y": 700.0,
        },
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body.get("error") == "cannot_cast"
    assert "cleric" in body.get("expected", "").lower()
