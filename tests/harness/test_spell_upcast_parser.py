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


def test_ignores_per_two_level_scaling():
    # Flame Blade et al. scale "for every two slot levels" — not
    # representable by the per-level scaler, so the parser bails.
    assert parse_upcast_dice(
        "the damage increases by 1d6 for every two slot levels above 2nd"
    ) == {}


def test_ignores_instance_scaling():
    # "one more dart" is instance scaling (extra_targets_per_slot_above_base),
    # not dice — no dice term, so no match.
    assert parse_upcast_dice(
        "the spell creates one more dart for each slot level above 1st"
    ) == {}


def test_ignores_flat_bonus():
    assert parse_upcast_dice(
        "the target's hit point maximum increases by 5 for each slot "
        "level above 2nd"
    ) == {}


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
