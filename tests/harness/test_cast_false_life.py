"""False Life — Sorcerer/Wizard L1, Phase 4 rider/bonus-scaling third
consumer and the first *linear-additive* shape.

v2.423.0 — Magic Weapon and Elemental Weapon step their bonus in tiers;
False Life climbs a flat +5 temp HP **per slot level** with no plateau —
the same linear shape as the Phase 3 count-additive family. RAW PHB
p.238: 1d4+4 temp HP base; "when you cast this spell using a spell slot
of 2nd level or higher, you gain 5 additional temporary hit points for
each slot level above 1st." The new `_SPELL_BONUS_ADDITIVE_MAP` (via
`_spell_bonus_additive_for_slot()`) returns only the per-slot additive
bonus; the 1d4+4 base is rolled server-side:

  - L1 → +0   (just 1d4+4)
  - L2 → +5
  - L3 → +10
  - L5 → +20

Unlike the weapon buffs, False Life grants temporary HP directly via
`_grant_temp_hp` (RAW non-stacking) and is self-only — no battle or
target needed. The deterministic assertions are on the additive `bonus`
and the `temp_hp == base_roll + bonus` identity (the random 1d4+4 base is
range-checked, not pinned). Caster fixtures: Thalindra Moonwhisper
(Wizard) for the ladder, Zara Emberfire (Sorcerer) for the gate; Krieger
Stonefist (Barbarian) for the 409 path.

Tests:
  - L1 base → bonus 0, base_roll in [5, 8], temp_hp == base_roll
  - L2 → bonus 5
  - L3 → bonus 10
  - L5 → bonus 20
  - Sorcerer caster (Zara) → passes the gate
  - 409 cannot_cast for a non-caster non-knower (Krieger Barbarian)
"""
from .conftest import CAMPAIGN_ID


def _assert_shape(body, slot_level, expected_bonus):
    assert body["feature"] == "false-life"
    assert body["slot_level"] == slot_level
    assert body["bonus"] == expected_bonus
    assert 5 <= body["base_roll"] <= 8
    assert body["temp_hp"] == body["base_roll"] + expected_bonus
    assert isinstance(body["temp_hp_applied"], bool)


async def test_false_life_base_slot_bonus0(gm_client, roster):
    """Thalindra casts at L1 base → bonus 0, temp_hp is just the 1d4+4
    base roll."""
    thalindra = roster["Thalindra Moonwhisper"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_false_life",
        json={"character_id": thalindra["id"], "slot_level": 1},
    )
    assert r.status_code == 200, r.text
    _assert_shape(r.json(), 1, 0)


async def test_false_life_l2_bonus5(gm_client, roster):
    """L2 → +5 additive temp HP on top of the base roll."""
    thalindra = roster["Thalindra Moonwhisper"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_false_life",
        json={"character_id": thalindra["id"], "slot_level": 2},
    )
    assert r.status_code == 200, r.text
    _assert_shape(r.json(), 2, 5)


async def test_false_life_l3_bonus10(gm_client, roster):
    """L3 → +10 (linear, no plateau)."""
    thalindra = roster["Thalindra Moonwhisper"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_false_life",
        json={"character_id": thalindra["id"], "slot_level": 3},
    )
    assert r.status_code == 200, r.text
    _assert_shape(r.json(), 3, 10)


async def test_false_life_l5_bonus20(gm_client, roster):
    """L5 → +20 (4 slots above 1st × 5); confirms the unbounded climb."""
    thalindra = roster["Thalindra Moonwhisper"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_false_life",
        json={"character_id": thalindra["id"], "slot_level": 5},
    )
    assert r.status_code == 200, r.text
    _assert_shape(r.json(), 5, 20)


async def test_false_life_sorcerer_caster_passes_gate(gm_client, roster):
    """Zara (Sorcerer) isn't a Wizard but Sorcerer is in the caster set →
    the cast succeeds."""
    zara = roster["Zara Emberfire"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_false_life",
        json={"character_id": zara["id"], "slot_level": 1},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["bonus"] == 0
    assert body["feature"] == "false-life"


async def test_false_life_cannot_cast_non_caster(gm_client, roster):
    """Krieger (Barbarian) doesn't know the spell and isn't a
    Sorcerer/Wizard → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_false_life",
        json={"character_id": krieger["id"], "slot_level": 1},
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body.get("error") == "cannot_cast"
    assert "sorcerer" in body.get("expected", "").lower()
