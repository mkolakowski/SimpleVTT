"""Phase 2A — damage assertions across the spell catalog.

For every (demo caster, damage-bearing spell) pair in the table
below: long-rest the caster, cast the spell against a target, and
assert the response's ``damage_total`` falls inside the declared
dice expression's [min, max] range.

This is the first commit of the spell-validation suite proposed in
``docs/plans/spell-validation-suite.md``. The plan's Phase 2A
target is "every spell with a damage action is range-checked"; the
ideal endpoint is the FULL 319-spell catalog, but the demo PCs
don't have every spell on their sheets (the ``/cast_spell``
endpoint reads the caster's sheet to find the spell at the given
index). Realistic coverage today is the demo casters' actual
loadouts — Thalindra (Wizard L5), Tavik (Cleric L4), Magnus
(Warlock L3) etc. Future commits add test-fixture casters per
the harness Phase 1.5 plan to lift coverage toward the full 319.

Per the plan, this is range-check only — exact-value assertion
via the v2.49.12 ``/api/test/dice/seed`` TEST_MODE endpoint comes
later (Phase 2A.2 if user demand surfaces).
"""
from __future__ import annotations

import pytest
import pytest_asyncio

from .conftest import CAMPAIGN_ID
from .spell_assert import assert_damage_in_range
from .spell_catalog import damage_actions, load_all_spells


# Session-scope catalog so the JSON files only get parsed once.
_SPELL_CATALOG = load_all_spells()
_BY_SLUG = {s["slug"]: s for s in _SPELL_CATALOG}


def _spell_damage_expr(slug: str) -> tuple[str, str]:
    """Return ``(damage_expr, damage_type)`` for a spell's primary
    damage action. Pulls from the catalog so the test reflects the
    SRD JSON's declared mechanics. Raises if the spell has no damage
    action — the table below should only list damage-bearing spells.
    """
    spell = _BY_SLUG.get(slug)
    if not spell:
        pytest.skip(f"spell {slug!r} not in catalog")
    actions = damage_actions(spell)
    if not actions:
        pytest.skip(f"spell {slug!r} has no damage action")
    a = actions[0]
    return (a["damage"] or "", a.get("damage_type") or "")


# (caster_name, spell_slug, spell_index, slot_level, base_dmg_expr, upcast_dice)
#
# Phase 2A v1 — scope intentionally tight: single-target ATTACK-ROLL
# spells where the response carries a clean ``auto_attack_damage_rolled``
# integer and the dice expression is the base damage (no per-beam
# variants, no auto-hit darts, no save spells). The endpoint's
# response shape varies per spell category — save spells, multi-
# beam spells (Scorching Ray, Eldritch Blast), and auto-hit force-
# damage spells (Magic Missile) each use different broadcast fields
# that need their own parameterized table.
#
# spell_index comes from the caster's demo-seed spell list ordering
# in app/demo_seed.py — stable across demo reseeds.
# base_dmg_expr is the AT-LEVEL expression (Fire Bolt at Lv 5 is
# 2d10, not the base 1d10). upcast_dice is the extra dice added when
# casting at a higher slot than the spell's natural level.
#
# Cantrip scaling note: Fire Bolt etc. scale with CASTER LEVEL
# (5/11/17). Thalindra (Wizard L5) hits the 2-dice tier.
#
# Add new rows as more attack-roll spells gain coverage. The save /
# multi-beam / auto-hit variants are filed below for follow-up
# commits — they need separate test infrastructure.
DAMAGE_SPELL_CASES: list[tuple[str, str, int, int, str, str]] = [
    # Fire Bolt (cantrip, single-target ranged spell attack).
    # At Wizard L5 → 2d10 fire. Range [2, 20].
    ("Thalindra Moonwhisper", "fire-bolt", 0, 0, "2d10", ""),
]


@pytest_asyncio.fixture
async def long_rested_caster(gm_client, roster):
    """Returns a helper that long-rests a named PC before each cast.
    Each parameterized case calls this once so the spell slot pool is
    fresh — important because a single test file casts 8 leveled
    spells in sequence and Thalindra's slot pool is 4 × L1 + 3 × L2
    + 2 × L3 + 1 × L4 + 1 × L5 = 11 slots total.
    """
    async def _rest(caster_name: str) -> dict:
        char = roster[caster_name]
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{char['id']}/rest",
            json={"type": "long"},
        )
        return char
    return _rest


async def _seed_target_bandit(gm_client) -> str:
    """Seed a single high-HP bandit combatant the cast can target.
    Returns the combatant id. High HP (200) so even a max-roll
    Fireball doesn't kill the bandit — auto_apply isn't on, so the
    HP is mostly decorative, but a live target makes the cast_spell
    pass its target-resolution branch instead of falling through
    to the untargeted path.
    """
    templates = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")).json()
    bandit = next(t for t in templates if "bandit" in t["name"].lower())
    combatant_id = "tok_dmgcatalog_target"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [{
                "id": combatant_id,
                "char_id": None,
                "token_template_id": bandit["id"],
                "name": "Damage Catalog Target",
                "initiative": 5,
                "hp_current": 200,
                "hp_max": 200,
                "buffs": [],
                "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
            }],
            "turn_index": 0,
            "round": 1,
            "active": True,
        },
    )
    return combatant_id


@pytest.mark.parametrize(
    "caster_name,spell_slug,spell_index,slot_level,base_dmg_expr,upcast_dice",
    DAMAGE_SPELL_CASES,
    ids=[f"{caster}-{slug}-L{slot}" for caster, slug, _, slot, _, _ in DAMAGE_SPELL_CASES],
)
async def test_spell_damage_in_declared_range(
    gm_client, gm_ws, long_rested_caster,
    caster_name, spell_slug, spell_index, slot_level, base_dmg_expr, upcast_dice,
):
    """For each (caster, spell) row: long-rest the caster, seed a
    target combatant, cast the spell, assert response's damage_total
    falls inside the declared dice expression's [min, max] bounds.

    Range-check only — exact-value assertion needs the TEST_MODE dice
    seed (filed for Phase 2A.2).
    """
    char = await long_rested_caster(caster_name)
    target_id = await _seed_target_bandit(gm_client)

    # v2.51.6: retry-on-miss. Attack-roll spells (Fire Bolt, Eldritch
    # Blast, etc.) only populate ``auto_attack_damage_rolled`` when the
    # d20 actually hits. With target AC 10 and +4 to hit, a d20 ≤ 5
    # misses (~25%), and the response then carries
    # ``auto_attack_damage_rolled: 0``. The pre-2.51.6 test had no
    # retry, so this flaked roughly every 4th CI run for Fire Bolt.
    # Loop up to 8 times to find a hit; range-check the SUCCESSFUL
    # roll. Damage-range coverage is unchanged.
    data = None
    for _ in range(8):
        await long_rested_caster(caster_name)
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": char["id"],
                "spell_index": spell_index,
                "slot_level": slot_level,
                "target_combatant_id": target_id,
                "override": True,
            },
        )
        assert resp.status_code == 200, (
            f"{caster_name} couldn't cast {spell_slug} at slot L{slot_level}: "
            f"{resp.status_code} {resp.text[:300]}"
        )
        data = resp.json()
        if int(data.get("auto_attack_damage_rolled") or 0) > 0:
            break
    damage_rolled = data.get("auto_attack_damage_rolled")
    assert isinstance(damage_rolled, int) and damage_rolled > 0, (
        f"{spell_slug}: no hit + non-zero damage in 8 attempts — "
        f"got {damage_rolled!r}. Full response: {data}"
    )
    # Sanity-check the catalog's declared expression — drift between
    # the test's expected expr and the JSON catches content edits
    # that change a spell's mechanical attributes.
    catalog_expr, catalog_type = _spell_damage_expr(spell_slug)
    assert catalog_expr, (
        f"{spell_slug}: catalog JSON has empty damage expression — "
        f"content edit may have dropped the damage field."
    )
    assert_damage_in_range(
        damage_rolled, base_dmg_expr,
        spell_name=spell_slug, slot_level=slot_level, upcast_dice=upcast_dice,
    )
    # Damage type should match the catalog (case-insensitive).
    if catalog_type:
        observed_type = (data.get("auto_attack_damage_type") or "").strip().lower()
        expected_type = catalog_type.strip().lower()
        assert observed_type == expected_type, (
            f"{spell_slug}: auto_attack_damage_type {observed_type!r} != catalog "
            f"{expected_type!r}"
        )
