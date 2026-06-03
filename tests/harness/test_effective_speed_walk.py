"""v2.99.98 — unit tests for `_effective_speed_walk` and
`_effective_speed_reduction_ft`.

Pure-Python tests; no HTTP / WS harness fixtures. Hosted alongside
the existing `test_range_parser.py` unit suite under
`tests/harness/` so the existing CI workflow picks them up.

The helpers walk `combatant.buffs[]` for `effects.speed_reduction_ft`
and subtract the sum from `combatant.speed_walk`. They're the
server-side mirror of the JS `_effectiveSpeedWalk` /
`_effectiveSpeedReductionFt` in tabletop.html — both consume the
v2.99.92 Lance of Lethargy buff format (and any future Slow / web
/ grease effect that installs the same field).
"""
import pytest

from app.content.effective_speed import (
    effective_speed_reduction_ft as _effective_speed_reduction_ft,
    effective_speed_walk as _effective_speed_walk,
)


# ---- _effective_speed_reduction_ft -------------------------------------

def test_no_buffs_returns_zero():
    assert _effective_speed_reduction_ft({"speed_walk": 30, "buffs": []}) == 0


def test_missing_buffs_field_returns_zero():
    assert _effective_speed_reduction_ft({"speed_walk": 30}) == 0


def test_none_combatant_returns_zero():
    assert _effective_speed_reduction_ft(None) == 0


def test_single_lance_of_lethargy_buff_returns_10():
    combatant = {
        "speed_walk": 30,
        "buffs": [
            {"key": "lance-of-lethargy",
             "effects": {"speed_reduction_ft": 10}},
        ],
    }
    assert _effective_speed_reduction_ft(combatant) == 10


def test_multiple_speed_reduction_buffs_sum():
    """Two stacking sources (e.g. Lance of Lethargy + Slow)
    should sum their reductions.
    """
    combatant = {
        "speed_walk": 30,
        "buffs": [
            {"key": "lance-of-lethargy",
             "effects": {"speed_reduction_ft": 10}},
            {"key": "slow",
             "effects": {"speed_reduction_ft": 15}},
        ],
    }
    assert _effective_speed_reduction_ft(combatant) == 25


def test_non_dict_effects_ignored():
    """Legacy condition buffs may carry a string list as
    ``effects`` rather than a dict — those should be silently
    skipped.
    """
    combatant = {
        "speed_walk": 30,
        "buffs": [
            {"key": "frightened",
             "effects": ["You can't willingly move closer to the source."]},
            {"key": "lance-of-lethargy",
             "effects": {"speed_reduction_ft": 10}},
        ],
    }
    assert _effective_speed_reduction_ft(combatant) == 10


def test_buffs_without_effects_field_ignored():
    combatant = {
        "speed_walk": 30,
        "buffs": [
            {"key": "blessed"},  # no effects field at all
            {"key": "lance-of-lethargy",
             "effects": {"speed_reduction_ft": 10}},
        ],
    }
    assert _effective_speed_reduction_ft(combatant) == 10


# ---- _effective_speed_walk ---------------------------------------------

def test_base_30_no_reduction_returns_30():
    assert _effective_speed_walk({"speed_walk": 30, "buffs": []}) == 30


def test_lance_of_lethargy_reduces_30_to_20():
    combatant = {
        "speed_walk": 30,
        "buffs": [
            {"key": "lance-of-lethargy",
             "effects": {"speed_reduction_ft": 10}},
        ],
    }
    assert _effective_speed_walk(combatant) == 20


def test_reduction_clamped_at_zero():
    """Reduction larger than base speed → 0, not negative.
    A stunned creature with a 30-ft base + a 60-ft web shouldn't
    grant negative movement.
    """
    combatant = {
        "speed_walk": 30,
        "buffs": [
            {"key": "ridiculous-reduction",
             "effects": {"speed_reduction_ft": 60}},
        ],
    }
    assert _effective_speed_walk(combatant) == 0


def test_missing_speed_walk_defaults_to_30():
    combatant = {
        "buffs": [
            {"key": "lance-of-lethargy",
             "effects": {"speed_reduction_ft": 10}},
        ],
    }
    assert _effective_speed_walk(combatant) == 20


def test_kael_40_speed_minus_10_returns_30():
    """Kael (Monk Lv 5 Unarmored Movement) has speed_walk 40.
    A Lance of Lethargy hit drops him to 30.
    """
    combatant = {
        "speed_walk": 40,
        "buffs": [
            {"key": "lance-of-lethargy",
             "effects": {"speed_reduction_ft": 10}},
        ],
    }
    assert _effective_speed_walk(combatant) == 30


def test_none_combatant_returns_30_default():
    assert _effective_speed_walk(None) == 30
