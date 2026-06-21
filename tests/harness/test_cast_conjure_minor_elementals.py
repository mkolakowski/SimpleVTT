"""Conjure Minor Elementals — Druid/Wizard L4, third Phase 3 multiplier consumer.

v2.416.0 — third (and final) consumer of the count-multiplier family on
`_SPELL_SUMMON_MAP`, after Conjure Animals and Conjure Woodland Beings.
RAW PHB p.225: summons elementals — one CR 2, two CR 1, four CR ½, or
eight CR ¼. Upcast: twice as many @6th, three times as many @8th. No
further scaling above L8 — the L8 tier carries through L9 via the
substrate's last-tier fallback.

The endpoint mirrors `/cast_conjure_woodland_beings`'s shape (base_level
4, ladder ×2 @6th / ×3 @8th, no ×4 tier) with one difference: a Druid
**or Wizard** class gate (Woodland Beings is Druid-only).

Caster fixtures: Mira Greenleaf (demo Druid) for the ladder; Thalindra
Moonwhisper (demo Wizard) for the Wizard-branch gate.

Tests:
  - L4 base ×1 (default count 8 → 8 elementals)
  - L5 still ×1 (within the base tier)
  - L6 doubles (base 2 → 4)
  - L8 triples (base 2 → 6)
  - L9 falls back to the last tier's ×3 multiplier (base 1 → 3)
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
        "id": f"tok_cme_{c['id']}", "char_id": c["id"], "name": c["name"],
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


async def test_cme_base_slot_no_multiplier(gm_client, roster):
    """Mira casts at L4 base slot → ×1 multiplier; base 8 → 8 elementals."""
    mira = roster["Mira Greenleaf"]
    await _seed_battle(gm_client, [_pc_cb(mira)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_conjure_minor_elementals",
        json={
            "character_id": mira["id"],
            "slot_level": 4,
            "x": 700.0, "y": 700.0, "spacing": 70,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    ids = [c["id"] for c in body["combatants"]]
    try:
        assert body["feature"] == "conjure-minor-elementals"
        assert body["base_count"] == 8
        assert body["slot_level"] == 4
        assert body["multiplier"] == 1
        assert body["count"] == 8
        assert len(ids) == 8
        for c in body["combatants"]:
            assert c["is_summon"] is True
            assert c["companion_key"] == "elemental-spirit"
            assert c["summoned_by"] == mira["id"]
    finally:
        await _dismiss_all(gm_client, ids)


async def test_cme_l5_still_base_tier(gm_client, roster):
    """L5 stays inside the L4–L5 base tier → ×1 multiplier."""
    mira = roster["Mira Greenleaf"]
    await _seed_battle(gm_client, [_pc_cb(mira)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_conjure_minor_elementals",
        json={
            "character_id": mira["id"],
            "count": 2, "slot_level": 5,
            "x": 700.0, "y": 700.0,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    ids = [c["id"] for c in body["combatants"]]
    try:
        assert body["base_count"] == 2
        assert body["slot_level"] == 5
        assert body["multiplier"] == 1
        assert body["count"] == 2
        assert len(ids) == 2
    finally:
        await _dismiss_all(gm_client, ids)


async def test_cme_l6_doubles(gm_client, roster):
    """L6 enters the second tier → ×2 multiplier. Base 2 → 4 elementals."""
    mira = roster["Mira Greenleaf"]
    await _seed_battle(gm_client, [_pc_cb(mira)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_conjure_minor_elementals",
        json={
            "character_id": mira["id"],
            "count": 2, "slot_level": 6,
            "x": 700.0, "y": 700.0,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    ids = [c["id"] for c in body["combatants"]]
    try:
        assert body["base_count"] == 2
        assert body["slot_level"] == 6
        assert body["multiplier"] == 2
        assert body["count"] == 4
        assert len(ids) == 4
    finally:
        await _dismiss_all(gm_client, ids)


async def test_cme_l8_triples(gm_client, roster):
    """L8 enters the third tier → ×3 multiplier. Base 2 → 6 elementals."""
    mira = roster["Mira Greenleaf"]
    await _seed_battle(gm_client, [_pc_cb(mira)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_conjure_minor_elementals",
        json={
            "character_id": mira["id"],
            "count": 2, "slot_level": 8,
            "x": 700.0, "y": 700.0,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    ids = [c["id"] for c in body["combatants"]]
    try:
        assert body["base_count"] == 2
        assert body["slot_level"] == 8
        assert body["multiplier"] == 3
        assert body["count"] == 6
        assert len(ids) == 6
    finally:
        await _dismiss_all(gm_client, ids)


async def test_cme_l9_last_tier_fallback(gm_client, roster):
    """L9 keeps the last tier's ×3 multiplier — no surprise ×4."""
    mira = roster["Mira Greenleaf"]
    await _seed_battle(gm_client, [_pc_cb(mira)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_conjure_minor_elementals",
        json={
            "character_id": mira["id"],
            "count": 1, "slot_level": 9,
            "x": 700.0, "y": 700.0,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    ids = [c["id"] for c in body["combatants"]]
    try:
        assert body["base_count"] == 1
        assert body["slot_level"] == 9
        assert body["multiplier"] == 3
        assert body["count"] == 3
        assert len(ids) == 3
    finally:
        await _dismiss_all(gm_client, ids)


async def test_cme_wizard_can_cast(gm_client, roster):
    """Thalindra (Wizard) passes the Druid/Wizard gate — the difference
    from Conjure Woodland Beings (Druid-only)."""
    thal = roster["Thalindra Moonwhisper"]
    await _seed_battle(gm_client, [_pc_cb(thal)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_conjure_minor_elementals",
        json={
            "character_id": thal["id"],
            "count": 2, "slot_level": 6,
            "x": 700.0, "y": 700.0,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    ids = [c["id"] for c in body["combatants"]]
    try:
        assert body["feature"] == "conjure-minor-elementals"
        assert body["multiplier"] == 2
        assert body["count"] == 4
        assert len(ids) == 4
    finally:
        await _dismiss_all(gm_client, ids)


async def test_cme_cannot_cast_non_caster(gm_client, roster):
    """Krieger (Barbarian) doesn't know the spell and isn't a Druid or
    Wizard → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _seed_battle(gm_client, [_pc_cb(krieger)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_conjure_minor_elementals",
        json={
            "character_id": krieger["id"],
            "slot_level": 4,
            "x": 700.0, "y": 700.0,
        },
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body.get("error") == "cannot_cast"
    assert "wizard" in body.get("expected", "").lower()


# ─── v2.540.0 — optional catalog-creature (elemental) override ────────


async def test_minor_elementals_catalog_elemental(gm_client, roster):
    """creature_slug=dust-mephit, count=4 (CR ½ ≤ the CR-½ tier) → four
    mephits with the catalog stat block (HP 17 / AC 12)."""
    mira = roster["Mira Greenleaf"]
    await _seed_battle(gm_client, [_pc_cb(mira)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_conjure_minor_elementals",
        json={"character_id": mira["id"], "count": 4,
              "creature_slug": "dust-mephit", "x": 700.0, "y": 700.0},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    ids = [c["id"] for c in body["combatants"]]
    try:
        assert len(body["combatants"]) == 4
        for c in body["combatants"]:
            assert c["companion_key"] == "dust-mephit"
            assert int(c["hp_max"]) == 17
            assert int(c["ac"]) == 12
    finally:
        await _dismiss_all(gm_client, ids)


async def test_minor_elementals_catalog_cr_too_high_400(gm_client, roster):
    """dust-mephit (CR ½) at count=8 (the CR-¼ tier) → 400."""
    mira = roster["Mira Greenleaf"]
    await _seed_battle(gm_client, [_pc_cb(mira)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_conjure_minor_elementals",
        json={"character_id": mira["id"], "count": 8,
              "creature_slug": "dust-mephit"},
    )
    assert r.status_code == 400, r.text


async def test_minor_elementals_catalog_non_elemental_400(gm_client, roster):
    """A non-elemental slug (wolf — Beast) → 400."""
    mira = roster["Mira Greenleaf"]
    await _seed_battle(gm_client, [_pc_cb(mira)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_conjure_minor_elementals",
        json={"character_id": mira["id"], "count": 2, "creature_slug": "wolf"},
    )
    assert r.status_code == 400, r.text
