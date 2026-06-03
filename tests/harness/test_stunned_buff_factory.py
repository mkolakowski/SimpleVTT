"""v2.99.115 — unit tests for `_make_stunned_buff` factory and
the `_make_stunning_strike_stunned_buff` thin wrapper.

The Stunned condition factory is the seventh speed-engine consumer
(after Lance of Lethargy, Slow, Web/Restrained, Hold Person/Monster
Paralyzed, and Grappled). Like the other condition factories, it
returns a buff with `key="stunned"`, `effects.speed_reduction_ft =
base` (full reduction → effective speed 0), and the canonical
Stunned raw_effects appended with source-specific bullets.

In-process tests; importing tabletop_routes pulls fastapi, so the
test guards the import with try/except + skips when fastapi isn't
installed locally. Runs in CI / docker fine.
"""
import pytest

try:
    from app.routes.tabletop_routes import (
        _make_stunned_buff,
        _make_stunning_strike_stunned_buff,
        _STUNNED_CORE_RAW_EFFECTS,
    )
    _IMPORT_OK = True
except ModuleNotFoundError:
    _IMPORT_OK = False


pytestmark = pytest.mark.skipif(
    not _IMPORT_OK,
    reason="fastapi not installed locally; runs in CI / docker image",
)


# ---- _make_stunned_buff ------------------------------------------------

def test_factory_returns_stunned_key():
    buff = _make_stunned_buff(
        target_speed_walk=30,
        source_char_id=1,
        source_char_name="Test",
        source="test-source",
        display_name="Test (Stunned)",
        icon="🧪",
        duration_rounds=1,
        concentration=False,
    )
    assert buff["key"] == "stunned"


def test_factory_speed_reduction_equals_base():
    buff = _make_stunned_buff(
        target_speed_walk=40,
        source_char_id=None,
        source_char_name="",
        source="x", display_name="x", icon="x",
        duration_rounds=1, concentration=False,
    )
    assert buff["effects"]["speed_reduction_ft"] == 40


def test_factory_zero_speed_target_clamped():
    buff = _make_stunned_buff(
        target_speed_walk=0,
        source_char_id=None,
        source_char_name="",
        source="x", display_name="x", icon="x",
        duration_rounds=1, concentration=False,
    )
    assert buff["effects"]["speed_reduction_ft"] == 0


def test_factory_none_speed_defaults_to_30():
    buff = _make_stunned_buff(
        target_speed_walk=None,
        source_char_id=None,
        source_char_name="",
        source="x", display_name="x", icon="x",
        duration_rounds=1, concentration=False,
    )
    assert buff["effects"]["speed_reduction_ft"] == 30


def test_factory_core_raw_effects_always_present():
    """All 5 canonical Stunned bullets in every buff."""
    buff = _make_stunned_buff(
        target_speed_walk=30,
        source_char_id=None,
        source_char_name="",
        source="x", display_name="x", icon="x",
        duration_rounds=1, concentration=False,
    )
    for line in _STUNNED_CORE_RAW_EFFECTS:
        assert line in buff["raw_effects"], (
            f"missing core Stunned bullet {line!r}; "
            f"got {buff['raw_effects']}"
        )


def test_factory_source_specific_raw_effects_extend():
    """Caller's source_specific list appends to core."""
    extra = ["Source-specific bullet"]
    buff = _make_stunned_buff(
        target_speed_walk=30,
        source_char_id=None,
        source_char_name="",
        source="x", display_name="x", icon="x",
        duration_rounds=1, concentration=False,
        source_specific_raw_effects=extra,
    )
    assert len(buff["raw_effects"]) == len(_STUNNED_CORE_RAW_EFFECTS) + 1
    assert extra[0] in buff["raw_effects"]


def test_factory_repeated_save_stamps_when_supplied():
    """When BOTH ability + DC are supplied, the buff gets the
    repeated-save stamps. Future "save to break free" Stunned
    spells (e.g. Power Word Stun variants) opt in this way.
    """
    buff = _make_stunned_buff(
        target_speed_walk=30,
        source_char_id=None,
        source_char_name="",
        source="x", display_name="x", icon="x",
        duration_rounds=10, concentration=False,
        repeated_save_ability="CON",
        repeated_save_dc=15,
    )
    assert buff.get("repeated_save_ability") == "CON"
    assert buff.get("repeated_save_dc") == 15


def test_factory_no_repeated_save_when_omitted():
    """Stunning Strike RAW has no save to break free — the
    factory omits the stamps when the kwargs aren't passed.
    """
    buff = _make_stunned_buff(
        target_speed_walk=30,
        source_char_id=None,
        source_char_name="",
        source="x", display_name="x", icon="x",
        duration_rounds=1, concentration=False,
    )
    assert "repeated_save_ability" not in buff
    assert "repeated_save_dc" not in buff


# ---- _make_stunning_strike_stunned_buff -------------------------------

def test_stunning_strike_wrapper_uses_stunned_key():
    buff = _make_stunning_strike_stunned_buff(
        target_speed_walk=40,
        source_char_id=42,
        source_char_name="Kael",
    )
    assert buff["key"] == "stunned"
    assert buff["source"] == "stunning-strike"
    assert buff["name"] == "Stunned (Stunning Strike)"
    assert buff["icon"] == "💫"


def test_stunning_strike_wrapper_duration_one_round():
    """RAW: "until the end of your next turn" — 1 round."""
    buff = _make_stunning_strike_stunned_buff(
        target_speed_walk=30,
        source_char_id=None,
        source_char_name="",
    )
    assert buff["duration_rounds"] == 1


def test_stunning_strike_wrapper_no_save_stamps():
    """RAW: no end-of-turn save to break free — fixed duration."""
    buff = _make_stunning_strike_stunned_buff(
        target_speed_walk=30,
        source_char_id=None,
        source_char_name="",
    )
    assert "repeated_save_ability" not in buff
    assert "repeated_save_dc" not in buff


def test_stunning_strike_wrapper_speed_reduction_equals_base():
    """40 ft base → reduction 40 (full → effective speed 0)."""
    buff = _make_stunning_strike_stunned_buff(
        target_speed_walk=40,
        source_char_id=None,
        source_char_name="",
    )
    assert buff["effects"]["speed_reduction_ft"] == 40


def test_stunning_strike_wrapper_includes_source_bullets():
    """The wrapper appends 3 Stunning Strike-specific raw_effects
    (trigger, save DC formula, no-save-to-break note).
    """
    buff = _make_stunning_strike_stunned_buff(
        target_speed_walk=30,
        source_char_id=None,
        source_char_name="",
    )
    # Core 5 + 3 specific = 8 bullets.
    assert len(buff["raw_effects"]) == len(_STUNNED_CORE_RAW_EFFECTS) + 3
    bullets_lower = " ".join(buff["raw_effects"]).lower()
    assert "ki point" in bullets_lower
    assert "con save" in bullets_lower
