"""Animate Dead — Cleric/Wizard L3, first Phase 3 additive-family consumer.

v2.417.0 — first consumer of the count-*additive* summon family
(`_SPELL_SUMMON_ADDITIVE_MAP` + `_spell_summon_additive_for_slot()`),
the second summon-scaling shape after the count-multiplier family.
RAW PHB p.212: create one undead servant (skeleton or zombie); upcast
animates two additional undead per slot level above 3rd. Unlike the
conjure spells, the count is *fully slot-determined* — there is no
chosen base-option `count`:

  - L3 → 1   (base)
  - L4 → 3   (1 + 2)
  - L5 → 5   (1 + 2×2)
  - L9 → 13  (1 + 2×6)

The endpoint gates on knowing Animate Dead OR being a Cleric / Wizard.
Caster fixtures: Brother Tavik Stonebrow (demo Cleric) for the ladder;
Thalindra Moonwhisper (demo Wizard) for the Wizard-branch gate.

Tests:
  - L3 base → 1 undead
  - L4 → 3 undead
  - L5 → 5 undead
  - L9 → 13 undead (top of the ladder)
  - Wizard caster (Thalindra) passes the class gate
  - 409 cannot_cast for a non-cleric/wizard non-knower (Krieger Barbarian)
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
        "id": f"tok_ad_{c['id']}", "char_id": c["id"], "name": c["name"],
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


async def test_animate_dead_base_slot_one(gm_client, roster):
    """Tavik casts at L3 base slot → exactly 1 undead servant."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _seed_battle(gm_client, [_pc_cb(tavik)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_animate_dead",
        json={
            "character_id": tavik["id"],
            "slot_level": 3,
            "x": 700.0, "y": 700.0, "spacing": 70,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    ids = [c["id"] for c in body["combatants"]]
    try:
        assert body["feature"] == "animate-dead"
        assert body["slot_level"] == 3
        assert body["count"] == 1
        assert len(ids) == 1
        for c in body["combatants"]:
            assert c["is_summon"] is True
            assert c["companion_key"] == "undead-servant"
            assert c["summoned_by"] == tavik["id"]
    finally:
        await _dismiss_all(gm_client, ids)


async def test_animate_dead_l4_three(gm_client, roster):
    """L4 → 1 + 2 = 3 undead."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _seed_battle(gm_client, [_pc_cb(tavik)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_animate_dead",
        json={
            "character_id": tavik["id"],
            "slot_level": 4,
            "x": 700.0, "y": 700.0,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    ids = [c["id"] for c in body["combatants"]]
    try:
        assert body["slot_level"] == 4
        assert body["count"] == 3
        assert len(ids) == 3
    finally:
        await _dismiss_all(gm_client, ids)


async def test_animate_dead_l5_five(gm_client, roster):
    """L5 → 1 + 2×2 = 5 undead."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _seed_battle(gm_client, [_pc_cb(tavik)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_animate_dead",
        json={
            "character_id": tavik["id"],
            "slot_level": 5,
            "x": 700.0, "y": 700.0,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    ids = [c["id"] for c in body["combatants"]]
    try:
        assert body["count"] == 5
        assert len(ids) == 5
    finally:
        await _dismiss_all(gm_client, ids)


async def test_animate_dead_l9_thirteen(gm_client, roster):
    """L9 → 1 + 2×6 = 13 undead (top of the ladder)."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _seed_battle(gm_client, [_pc_cb(tavik)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_animate_dead",
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
        assert body["count"] == 13
        assert len(ids) == 13
    finally:
        await _dismiss_all(gm_client, ids)


async def test_animate_dead_wizard_can_cast(gm_client, roster):
    """Thalindra (Wizard) passes the Cleric/Wizard gate → L4 = 3 undead."""
    thal = roster["Thalindra Moonwhisper"]
    await _seed_battle(gm_client, [_pc_cb(thal)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_animate_dead",
        json={
            "character_id": thal["id"],
            "slot_level": 4,
            "x": 700.0, "y": 700.0,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    ids = [c["id"] for c in body["combatants"]]
    try:
        assert body["feature"] == "animate-dead"
        assert body["count"] == 3
        assert len(ids) == 3
    finally:
        await _dismiss_all(gm_client, ids)


async def test_animate_dead_cannot_cast_non_caster(gm_client, roster):
    """Krieger (Barbarian) doesn't know the spell and isn't a Cleric or
    Wizard → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _seed_battle(gm_client, [_pc_cb(krieger)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_animate_dead",
        json={
            "character_id": krieger["id"],
            "slot_level": 3,
            "x": 700.0, "y": 700.0,
        },
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body.get("error") == "cannot_cast"
    assert "cleric" in body.get("expected", "").lower()
