"""Unit tests for ``app/content/range_parser.py``.

v2.49.74 — Phase 2B of the ruler/range plan. Pure-Python tests; no
HTTP / WS harness fixtures. Hosted under ``tests/harness/`` so the
existing CI workflow (``.github/workflows/test-harness.yml``) picks
them up without needing a new job. Doesn't import any fixtures, so
the conftest's expensive httpx-client setup is a no-op here.
"""
import pytest

from app.content.range_parser import max_range_ft, parse_range_ft


# ---- parse_range_ft ----------------------------------------------------

def test_self_returns_zero():
    assert parse_range_ft("Self") == 0
    assert parse_range_ft("self") == 0
    assert parse_range_ft("  Self  ") == 0


def test_self_with_radius_returns_zero():
    """Self-anchored emanations: range is Self (= 0); the radius is
    a separate AoE concern that doesn't gate the cast check."""
    assert parse_range_ft("Self (30-foot radius)") == 0
    assert parse_range_ft("Self (5-foot radius)") == 0
    assert parse_range_ft("Self (15-foot cube)") == 0
    assert parse_range_ft("Self (10-foot-radius sphere)") == 0


def test_touch_returns_five():
    """RAW: touch range = 5 ft melee reach."""
    assert parse_range_ft("Touch") == 5
    assert parse_range_ft("touch") == 5


def test_single_feet_band():
    assert parse_range_ft("5 feet") == 5
    assert parse_range_ft("30 feet") == 30
    assert parse_range_ft("60 feet") == 60
    assert parse_range_ft("90 feet") == 90
    assert parse_range_ft("120 feet") == 120
    assert parse_range_ft("150 feet") == 150
    assert parse_range_ft("300 feet") == 300
    assert parse_range_ft("500 feet") == 500


def test_feet_abbreviation():
    """Weapons use the abbreviated 'ft' form (5 ft, 60 ft)."""
    assert parse_range_ft("5 ft") == 5
    assert parse_range_ft("60 ft") == 60
    assert parse_range_ft("120 ft") == 120


def test_feet_alt_spellings():
    """Tolerate 'foot' singular + trailing period."""
    assert parse_range_ft("5 foot") == 5
    assert parse_range_ft("5 feet.") == 5
    assert parse_range_ft("60 ft.") == 60


def test_thrown_weapon_range():
    """Thrown / ranged weapons use the 'normal/long' band."""
    assert parse_range_ft("20/60 feet") == (20, 60)
    assert parse_range_ft("30/120 feet") == (30, 120)
    assert parse_range_ft("80/320 feet") == (80, 320)


def test_thrown_abbreviated():
    """Demo weapons in app/demo_seed.py use '20/60 ft' / '30/120 ft'."""
    assert parse_range_ft("20/60 ft") == (20, 60)
    assert parse_range_ft("30/120 ft") == (30, 120)
    assert parse_range_ft("100/400 ft") == (100, 400)


def test_mile_scale():
    """RAW: 1 mile = 5280 ft. Sending / Scrying use mile-scale."""
    assert parse_range_ft("1 mile") == 5280
    assert parse_range_ft("5 miles") == 5 * 5280
    assert parse_range_ft("500 miles") == 500 * 5280


def test_skip_strings_return_none():
    """RAW catch-alls Wizards uses for spells without numeric range."""
    assert parse_range_ft("Special") is None
    assert parse_range_ft("Unlimited") is None
    assert parse_range_ft("Sight") is None
    assert parse_range_ft("special") is None
    assert parse_range_ft("unlimited") is None
    assert parse_range_ft("sight") is None


def test_empty_inputs_return_none():
    assert parse_range_ft("") is None
    assert parse_range_ft("   ") is None
    assert parse_range_ft(None) is None


def test_garbage_returns_none():
    """Unparseable strings must NOT raise; return None so the caller
    treats them as 'skip the range check' (conservative default)."""
    assert parse_range_ft("not a range") is None
    assert parse_range_ft("60") is None        # number without unit
    assert parse_range_ft("ft 60") is None     # malformed
    assert parse_range_ft("60/ft") is None
    assert parse_range_ft("60 leagues") is None


# ---- max_range_ft ----------------------------------------------------

def test_max_range_passthrough_int():
    assert max_range_ft(60) == 60
    assert max_range_ft(0) == 0
    assert max_range_ft(5) == 5


def test_max_range_collapses_thrown():
    """Thrown weapons report the LONG range as the absolute reach.
    Disadvantage at long range is a separate concern."""
    assert max_range_ft((20, 60)) == 60
    assert max_range_ft((30, 120)) == 120
    assert max_range_ft((80, 320)) == 320


def test_max_range_none_passthrough():
    assert max_range_ft(None) is None


def test_combined_pipeline():
    """End-to-end: parse a string + collapse to a single int."""
    assert max_range_ft(parse_range_ft("60 feet")) == 60
    assert max_range_ft(parse_range_ft("30/120 ft")) == 120
    assert max_range_ft(parse_range_ft("Touch")) == 5
    assert max_range_ft(parse_range_ft("Self")) == 0
    assert max_range_ft(parse_range_ft("Self (30-foot radius)")) == 0
    assert max_range_ft(parse_range_ft("Special")) is None
    assert max_range_ft(parse_range_ft("not a range")) is None


# ---- SRD content compatibility checks -------------------------------

@pytest.mark.parametrize("range_str,expected", [
    # The 17 unique range strings surveyed from
    # app/data/local/dnd5e/spells/*.json. Pin every one so a future
    # SRD-content refresh that drifts the strings fails this test
    # rather than silently breaking range enforcement.
    ("Self", 0),
    ("Touch", 5),
    ("60 feet", 60),
    ("30 feet", 30),
    ("120 feet", 120),
    ("90 feet", 90),
    ("10 feet", 10),
    ("150 feet", 150),
    ("300 feet", 300),
    ("1 mile", 5280),
    ("100 feet", 100),
    ("500 feet", 500),
    ("Sight", None),
    ("Special", None),
    ("Unlimited", None),
    ("500 miles", 500 * 5280),
    ("5 feet", 5),
])
def test_srd_spell_ranges(range_str, expected):
    assert parse_range_ft(range_str) == expected
