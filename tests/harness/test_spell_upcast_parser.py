"""v2.125.0 — unit tests for `parse_upcast_dice`.

Pure-Python test (no HTTP/WS harness), mirroring
`test_monster_action_desc_parser.py`. The helper derives a spell's
per-slot up-cast dice from its free-text `higher_level` clause so the
~285 SRD spells that carry the rule only in prose can scale through the
v2.110.0 resolver without a hand-authored `damage_per_slot` field. The
resolver consults the parser ONLY when no structured field is present
(manual JSON wins) and only applies it to an action that already has a
base damage/healing expr — these tests pin the conservative parse so a
future phrasing change can't silently start mis-scaling casts.
"""
from app.content.spell_upcast_parse import (
    parse_upcast_dice,
    upcast_target_count,
    upcast_pool_dice,
    scale_flat_for_upcast,
)


def test_parses_per_slot_damage():
    assert parse_upcast_dice(
        "the damage increases by 1d6 for each slot level above 3rd"
    ) == {"damage_per_slot": "1d6"}


def test_parses_per_slot_healing():
    assert parse_upcast_dice(
        "the healing increases by 1d8 for each slot level above 1st"
    ) == {"healing_per_slot": "1d8"}


def test_parses_multi_die_term():
    assert parse_upcast_dice(
        "the damage increases by 2d6 for each slot level above 7th"
    ) == {"damage_per_slot": "2d6"}


def test_ignores_cantrip_character_level_scaling():
    # Cantrips scale by character level ("when you reach 5th level"), not
    # a slot — there's no slot to up-cast, so the parser must not match.
    assert parse_upcast_dice(
        "This spell's damage increases by 1d8 when you reach 5th level "
        "(2d8), 11th level (3d8), and 17th level (4d8)."
    ) == {}


def test_parses_per_two_level_damage():
    # v2.129.0 — Flame Blade-style "+1d6 for every two slot levels above 2nd"
    # now returns the dice + `upcast_step: 2` so the resolver can scale by
    # `(slot_level - base) // 2`.
    assert parse_upcast_dice(
        "the damage increases by 1d6 for every two slot levels above 2nd"
    ) == {"damage_per_slot": "1d6", "upcast_step": 2}


def test_parses_per_two_level_damage_spiritual_weapon():
    # Spiritual Weapon's prose includes "the 2nd" — the regex must accept
    # the "above the 2nd" variant alongside "above 2nd".
    assert parse_upcast_dice(
        "the damage increases by 1d8 for every two slot levels above the 2nd"
    ) == {"damage_per_slot": "1d8", "upcast_step": 2}


def test_parses_per_two_level_healing():
    # Synthetic: no SRD spell uses per-two healing, but the parser must
    # classify heal/damage symmetrically with the per-1 path.
    assert parse_upcast_dice(
        "the healing increases by 1d6 for every two slot levels above 1st"
    ) == {"healing_per_slot": "1d6", "upcast_step": 2}


def test_ignores_instance_scaling():
    # "one more dart" is instance scaling (extra_targets_per_slot_above_base),
    # not dice — no dice term, so no match.
    assert parse_upcast_dice(
        "the spell creates one more dart for each slot level above 1st"
    ) == {}


def test_parses_flat_healing_aid():
    # v2.130.0 — Aid: "a target's hit points increase by an additional 5
    # for each slot level above 2nd". "hit points" in the clause routes
    # the bonus to flat_healing_per_slot.
    assert parse_upcast_dice(
        "a target's hit points increase by an additional 5 for each "
        "slot level above 2nd"
    ) == {"flat_healing_per_slot": 5}


def test_parses_flat_healing_heal():
    # v2.130.0 — Heal: "the amount of healing increases by 10 for each
    # slot level above 6th". "healing" classifier → flat_healing_per_slot.
    assert parse_upcast_dice(
        "the amount of healing increases by 10 for each slot level above 6th"
    ) == {"flat_healing_per_slot": 10}


def test_parses_flat_healing_false_life():
    # v2.130.0 — False Life: "you gain 5 additional temporary hit points
    # for each slot level above 1st". The "hit points" AFTER the dice term
    # still routes to healing because v2.130.0 classifier searches the
    # full clause, not just the lead.
    assert parse_upcast_dice(
        "you gain 5 additional temporary hit points for each slot "
        "level above 1st"
    ) == {"flat_healing_per_slot": 5}


def test_flat_does_not_match_dice_clause():
    # Regression guard: "1d6 for each slot level above 3rd" must NOT
    # surface as flat_damage_per_slot: 6 (the "6" inside the dice
    # term). The dice-pattern regex fires first; the flat regex's
    # `\b\d+\b` boundary excludes digits inside a dice term.
    assert parse_upcast_dice(
        "the damage increases by 1d6 for each slot level above 3rd"
    ) == {"damage_per_slot": "1d6"}


def test_empty_or_missing():
    assert parse_upcast_dice("") == {}
    assert parse_upcast_dice(None) == {}


# ── v2.127.0 — upcast_target_count (Approach C: shared target-count math) ──


def test_target_count_hold_person():
    # base L2, 1 +1/slot: L2→1, L3→2, L4→3 (replaces max(1, slot_level-1)).
    assert upcast_target_count(2, base_level=2) == 1
    assert upcast_target_count(3, base_level=2) == 2
    assert upcast_target_count(4, base_level=2) == 3


def test_target_count_hold_monster():
    # base L5, 1 +1/slot: L5→1, L6→2, L9→5 (replaces max(1, slot_level-4)).
    assert upcast_target_count(5, base_level=5) == 1
    assert upcast_target_count(6, base_level=5) == 2
    assert upcast_target_count(9, base_level=5) == 5


def test_target_count_clamps_and_params():
    # below base level never returns < base_targets.
    assert upcast_target_count(1, base_level=5) == 1
    # custom base_targets + per_slot (e.g. Bless: 3 + 1/slot above L1).
    assert upcast_target_count(1, base_level=1, base_targets=3) == 3
    assert upcast_target_count(3, base_level=1, base_targets=3) == 5


def test_pool_dice_sleep():
    # Sleep base L1, 5d8 +2d8/slot: L1→5, L2→7, L3→9 (replaces
    # `5 + max(0, slot_level - 1) * 2`).
    assert upcast_pool_dice(1, base_level=1, base_dice=5, per_slot_dice=2) == 5
    assert upcast_pool_dice(2, base_level=1, base_dice=5, per_slot_dice=2) == 7
    assert upcast_pool_dice(3, base_level=1, base_dice=5, per_slot_dice=2) == 9


def test_pool_dice_clamps_below_base():
    assert upcast_pool_dice(0, base_level=1, base_dice=5, per_slot_dice=2) == 5


# ── v2.130.0 — scale_flat_for_upcast (Heal-style flat-bonus scaler) ──


def test_flat_scaler_pure_flat_base():
    # Heal: base "70", +10/slot, 1 extra slot → "80". 3 extras → "100".
    assert scale_flat_for_upcast("70", 10, 1) == "80"
    assert scale_flat_for_upcast("70", 10, 3) == "100"


def test_flat_scaler_dice_plus_flat_base():
    # False Life: base "1d4+4", +5/slot, 1 extra → "1d4+9" (bumps the +N).
    assert scale_flat_for_upcast("1d4+4", 5, 1) == "1d4+9"
    assert scale_flat_for_upcast("1d4+4", 5, 2) == "1d4+14"


def test_flat_scaler_pure_dice_base():
    # Pure dice base ("1d8" with no modifier) gets the flat appended as +N.
    assert scale_flat_for_upcast("1d8", 5, 1) == "1d8+5"


def test_flat_scaler_base_unchanged_on_no_op():
    # extra_levels=0 → base unchanged. Defends low-slot casts.
    assert scale_flat_for_upcast("70", 10, 0) == "70"
    # Missing per-slot → base unchanged.
    assert scale_flat_for_upcast("70", 0, 5) == "70"
    # Unparseable base ("1d8+1d6") → no-op rather than corrupt.
    assert scale_flat_for_upcast("1d8+1d6", 5, 1) == "1d8+1d6"
