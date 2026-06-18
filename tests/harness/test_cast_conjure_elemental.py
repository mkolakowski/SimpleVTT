"""Conjure Elemental — Druid/Wizard L5, first Phase 3 CR-increase consumer.

v2.418.0 — first consumer of the summon *CR-increase* family
(`_SPELL_SUMMON_CR_MAP` + `_spell_summon_cr_for_slot()`), the third and
final summon-scaling shape after the count-multiplier and count-additive
families. RAW PHB p.225: an elemental of CR 5 or lower appears; upcast
increases the challenge rating by 1 per slot level above 5th. Unlike the
*count*-scaling conjure spells, exactly **one** elemental is summoned and
its CR climbs with the slot:

  - L5 → CR 5   (base)
  - L6 → CR 6
  - L7 → CR 7
  - L9 → CR 9   (top of the ladder)

The endpoint gates on knowing Conjure Elemental OR being a Druid /
Wizard. Caster fixtures: Mira Greenleaf (demo Druid) for the ladder;
Thalindra Moonwhisper (demo Wizard) for the Wizard-branch gate.

Tests:
  - L5 base → 1 elemental, CR 5
  - L6 → CR 6
  - L9 → CR 9 (top of the ladder)
  - Wizard caster (Thalindra) passes the class gate
  - 409 cannot_cast for a non-druid/wizard non-knower (Krieger Barbarian)
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
        "id": f"tok_ce_{c['id']}", "char_id": c["id"], "name": c["name"],
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


async def test_conjure_elemental_base_slot_cr5(gm_client, roster):
    """Mira casts at L5 base slot → exactly 1 elemental at CR 5."""
    mira = roster["Mira Greenleaf"]
    await _seed_battle(gm_client, [_pc_cb(mira)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_conjure_elemental",
        json={
            "character_id": mira["id"],
            "slot_level": 5,
            "x": 700.0, "y": 700.0,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    ids = [c["id"] for c in body["combatants"]]
    try:
        assert body["feature"] == "conjure-elemental"
        assert body["slot_level"] == 5
        assert body["count"] == 1
        assert body["challenge_rating"] == 5
        assert len(ids) == 1
        for c in body["combatants"]:
            assert c["is_summon"] is True
            assert c["companion_key"] == "elemental-spirit"
            assert c["summoned_by"] == mira["id"]
    finally:
        await _dismiss_all(gm_client, ids)


async def test_conjure_elemental_l6_cr6(gm_client, roster):
    """L6 → CR 6 (+1 per slot above 5th), still exactly 1 elemental."""
    mira = roster["Mira Greenleaf"]
    await _seed_battle(gm_client, [_pc_cb(mira)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_conjure_elemental",
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
        assert body["slot_level"] == 6
        assert body["count"] == 1
        assert body["challenge_rating"] == 6
        assert len(ids) == 1
    finally:
        await _dismiss_all(gm_client, ids)


async def test_conjure_elemental_l9_cr9(gm_client, roster):
    """L9 → CR 9 (top of the ladder), still exactly 1 elemental."""
    mira = roster["Mira Greenleaf"]
    await _seed_battle(gm_client, [_pc_cb(mira)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_conjure_elemental",
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


async def test_conjure_elemental_wizard_can_cast(gm_client, roster):
    """Thalindra (Wizard) passes the Druid/Wizard gate → L5 = CR 5."""
    thal = roster["Thalindra Moonwhisper"]
    await _seed_battle(gm_client, [_pc_cb(thal)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_conjure_elemental",
        json={
            "character_id": thal["id"],
            "slot_level": 5,
            "x": 700.0, "y": 700.0,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    ids = [c["id"] for c in body["combatants"]]
    try:
        assert body["feature"] == "conjure-elemental"
        assert body["count"] == 1
        assert body["challenge_rating"] == 5
        assert len(ids) == 1
    finally:
        await _dismiss_all(gm_client, ids)


async def test_conjure_elemental_cannot_cast_non_caster(gm_client, roster):
    """Krieger (Barbarian) doesn't know the spell and isn't a Druid or
    Wizard → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _seed_battle(gm_client, [_pc_cb(krieger)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_conjure_elemental",
        json={
            "character_id": krieger["id"],
            "slot_level": 5,
            "x": 700.0, "y": 700.0,
        },
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body.get("error") == "cannot_cast"
    assert "druid" in body.get("expected", "").lower()
