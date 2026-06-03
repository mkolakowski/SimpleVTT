"""v2.99.106 — unit tests for `_make_restrained_buff` factory.

The Restrained condition refactor extracts Web's mechanical bits
into a shared factory that future Grappled / Hold spells / monster
grappler features can call with their own source-specific args.

Tests cover:
  - the factory returns key="restrained" (canonical condition key)
  - effects.speed_reduction_ft = base (full reduction → speed 0)
  - core raw_effects (4 canonical Restrained bullets) are always
    present
  - source_specific_raw_effects extend (not replace) the core list
  - source attribution fields plumb through
  - `_make_web_buff` is now a thin wrapper that produces a
    key="restrained" buff with source="web-spell" + 2 web-specific
    raw_effects appended

Pure-Python tests; importing tabletop_routes pulls fastapi, so
these only run inside the docker / CI image (matches
test_effective_speed_walk.py pattern — except those went into a
leaf module). For this commit, the factory is far enough into the
routes module that splitting it out would cost more than it
saves; the test runs in CI fine via the docker image.
"""
import pytest

try:
    from app.routes.tabletop_routes import (
        _make_restrained_buff,
        _make_web_buff,
        _RESTRAINED_CORE_RAW_EFFECTS,
    )
    _IMPORT_OK = True
except ModuleNotFoundError:  # local host without fastapi installed
    _IMPORT_OK = False


pytestmark = pytest.mark.skipif(
    not _IMPORT_OK,
    reason="fastapi not installed locally; runs in CI / docker image",
)


def test_factory_returns_restrained_key():
    buff = _make_restrained_buff(
        target_speed_walk=30,
        source_char_id=1,
        source_char_name="Test",
        source="test-source",
        display_name="Test (Restrained)",
        icon="🧪",
        duration_rounds=10,
        concentration=False,
    )
    assert buff["key"] == "restrained"


def test_factory_speed_reduction_equals_base():
    """Full reduction: target with 40 ft base → reduction 40."""
    buff = _make_restrained_buff(
        target_speed_walk=40,
        source_char_id=None,
        source_char_name="",
        source="x", display_name="x", icon="x",
        duration_rounds=10, concentration=False,
    )
    assert buff["effects"]["speed_reduction_ft"] == 40


def test_factory_zero_speed_target_clamped():
    buff = _make_restrained_buff(
        target_speed_walk=0,
        source_char_id=None,
        source_char_name="",
        source="x", display_name="x", icon="x",
        duration_rounds=10, concentration=False,
    )
    assert buff["effects"]["speed_reduction_ft"] == 0


def test_factory_none_speed_defaults_to_30():
    buff = _make_restrained_buff(
        target_speed_walk=None,
        source_char_id=None,
        source_char_name="",
        source="x", display_name="x", icon="x",
        duration_rounds=10, concentration=False,
    )
    assert buff["effects"]["speed_reduction_ft"] == 30


def test_factory_core_raw_effects_always_present():
    """All 4 canonical Restrained bullets in every buff."""
    buff = _make_restrained_buff(
        target_speed_walk=30,
        source_char_id=None,
        source_char_name="",
        source="x", display_name="x", icon="x",
        duration_rounds=10, concentration=False,
    )
    for line in _RESTRAINED_CORE_RAW_EFFECTS:
        assert line in buff["raw_effects"], (
            f"missing core Restrained bullet {line!r}; got {buff['raw_effects']}"
        )


def test_factory_source_specific_raw_effects_extend():
    """Caller's source_specific list appends to (doesn't replace)
    the core list.
    """
    extra = ["Source-specific bullet A", "Source-specific bullet B"]
    buff = _make_restrained_buff(
        target_speed_walk=30,
        source_char_id=None,
        source_char_name="",
        source="x", display_name="x", icon="x",
        duration_rounds=10, concentration=False,
        source_specific_raw_effects=extra,
    )
    # All 4 core + 2 extras = 6.
    assert len(buff["raw_effects"]) == len(_RESTRAINED_CORE_RAW_EFFECTS) + 2
    for line in extra:
        assert line in buff["raw_effects"]


def test_factory_source_attribution_plumbs_through():
    buff = _make_restrained_buff(
        target_speed_walk=30,
        source_char_id=42,
        source_char_name="Thalindra",
        source="web-spell",
        display_name="Webbed (Restrained)",
        icon="🕸",
        duration_rounds=600,
        concentration=True,
    )
    assert buff["source"] == "web-spell"
    assert buff["source_char_id"] == 42
    assert buff["source_char_name"] == "Thalindra"
    assert buff["name"] == "Webbed (Restrained)"
    assert buff["icon"] == "🕸"
    assert buff["concentration"] is True
    assert buff["duration_rounds"] == 600


def test_web_buff_uses_restrained_key_and_extends_raw_effects():
    """Web's thin wrapper produces a restrained buff with the
    web-specific raw_effects appended.
    """
    buff = _make_web_buff(
        target_speed_walk=40,
        source_char_id=42,
        source_char_name="Thalindra",
    )
    assert buff["key"] == "restrained"
    assert buff["source"] == "web-spell"
    assert buff["name"] == "Webbed (Restrained)"
    assert buff["icon"] == "🕸"
    assert buff["effects"]["speed_reduction_ft"] == 40
    # Core Restrained + 2 Web-specific raw effects.
    assert len(buff["raw_effects"]) == len(_RESTRAINED_CORE_RAW_EFFECTS) + 2
    web_lines = " ".join(buff["raw_effects"]).lower()
    assert "break free" in web_lines
    assert "flammable" in web_lines
