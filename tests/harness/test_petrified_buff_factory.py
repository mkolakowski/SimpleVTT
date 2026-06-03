"""v2.99.119 — unit tests for `_make_petrified_buff` factory and
the `_make_flesh_to_stone_petrified_buff` thin wrapper.

The Petrified condition factory is the eighth speed-engine consumer
(after Lance of Lethargy, Slow, Web/Restrained, Hold Person/Monster
Paralyzed, Grappled, Stunned). RAW Petrified is the strongest
speed→0 condition — adds resistance to all damage + immunity to
poison/disease + weight ×10 + aging stops on top of the standard
Paralyzed mechanics.

In-process tests; importing tabletop_routes pulls fastapi, so the
test guards the import with try/except + skips when fastapi isn't
installed locally. Runs in CI / docker fine.
"""
import pytest

try:
    from app.routes.tabletop_routes import (
        _make_petrified_buff,
        _make_flesh_to_stone_petrified_buff,
        _PETRIFIED_CORE_RAW_EFFECTS,
    )
    _IMPORT_OK = True
except ModuleNotFoundError:
    _IMPORT_OK = False


pytestmark = pytest.mark.skipif(
    not _IMPORT_OK,
    reason="fastapi not installed locally; runs in CI / docker image",
)


# ---- _make_petrified_buff ----------------------------------------------

def test_factory_returns_petrified_key():
    buff = _make_petrified_buff(
        target_speed_walk=30,
        source_char_id=1,
        source_char_name="Test",
        source="test-source",
        display_name="Test (Petrified)",
        icon="🧪",
        duration_rounds=10,
        concentration=False,
    )
    assert buff["key"] == "petrified"


def test_factory_speed_reduction_equals_base():
    buff = _make_petrified_buff(
        target_speed_walk=40,
        source_char_id=None,
        source_char_name="",
        source="x", display_name="x", icon="x",
        duration_rounds=10, concentration=False,
    )
    assert buff["effects"]["speed_reduction_ft"] == 40


def test_factory_zero_speed_target_clamped():
    buff = _make_petrified_buff(
        target_speed_walk=0,
        source_char_id=None,
        source_char_name="",
        source="x", display_name="x", icon="x",
        duration_rounds=10, concentration=False,
    )
    assert buff["effects"]["speed_reduction_ft"] == 0


def test_factory_none_speed_defaults_to_30():
    buff = _make_petrified_buff(
        target_speed_walk=None,
        source_char_id=None,
        source_char_name="",
        source="x", display_name="x", icon="x",
        duration_rounds=10, concentration=False,
    )
    assert buff["effects"]["speed_reduction_ft"] == 30


def test_factory_core_raw_effects_always_present():
    """All 8 canonical Petrified bullets in every buff."""
    buff = _make_petrified_buff(
        target_speed_walk=30,
        source_char_id=None,
        source_char_name="",
        source="x", display_name="x", icon="x",
        duration_rounds=10, concentration=False,
    )
    for line in _PETRIFIED_CORE_RAW_EFFECTS:
        assert line in buff["raw_effects"], (
            f"missing core Petrified bullet {line!r}; "
            f"got {buff['raw_effects']}"
        )


def test_factory_includes_resistance_to_all_damage_bullet():
    """Petrified is the only condition factory whose canonical
    raw_effects include 'resistance to all damage' (RAW PHB p.290).
    Pin it explicitly.
    """
    buff = _make_petrified_buff(
        target_speed_walk=30,
        source_char_id=None,
        source_char_name="",
        source="x", display_name="x", icon="x",
        duration_rounds=10, concentration=False,
    )
    bullets_lower = " ".join(buff["raw_effects"]).lower()
    assert "resistance to all damage" in bullets_lower, buff["raw_effects"]
    assert "immune to poison" in bullets_lower, buff["raw_effects"]


def test_factory_repeated_save_stamps_when_supplied():
    buff = _make_petrified_buff(
        target_speed_walk=30,
        source_char_id=None,
        source_char_name="",
        source="x", display_name="x", icon="x",
        duration_rounds=10, concentration=True,
        repeated_save_ability="CON",
        repeated_save_dc=17,
    )
    assert buff.get("repeated_save_ability") == "CON"
    assert buff.get("repeated_save_dc") == 17


def test_factory_no_repeated_save_when_omitted():
    buff = _make_petrified_buff(
        target_speed_walk=30,
        source_char_id=None,
        source_char_name="",
        source="x", display_name="x", icon="x",
        duration_rounds=10, concentration=False,
    )
    assert "repeated_save_ability" not in buff
    assert "repeated_save_dc" not in buff


# ---- _make_flesh_to_stone_petrified_buff -------------------------------

def test_flesh_to_stone_wrapper_uses_petrified_key():
    buff = _make_flesh_to_stone_petrified_buff(
        target_speed_walk=40,
        source_char_id=42,
        source_char_name="Caster",
        spell_save_dc=15,
    )
    assert buff["key"] == "petrified"
    assert buff["source"] == "flesh-to-stone-spell"
    assert buff["name"] == "Petrified (Flesh to Stone)"
    assert buff["icon"] == "🗿"


def test_flesh_to_stone_wrapper_duration_10_rounds():
    """RAW: concentration up to 1 minute = 10 rounds."""
    buff = _make_flesh_to_stone_petrified_buff(
        target_speed_walk=30,
        source_char_id=None,
        source_char_name="",
    )
    assert buff["duration_rounds"] == 10
    assert buff["concentration"] is True


def test_flesh_to_stone_wrapper_stamps_con_save():
    """RAW: CON save at end of each turn (3 successes ends).
    Wrapper stamps the framework hooks via repeated_save_ability=
    "CON" and the caller-supplied DC.
    """
    buff = _make_flesh_to_stone_petrified_buff(
        target_speed_walk=30,
        source_char_id=None,
        source_char_name="",
        spell_save_dc=16,
    )
    assert buff.get("repeated_save_ability") == "CON"
    assert buff.get("repeated_save_dc") == 16


def test_flesh_to_stone_wrapper_no_dc_omits_stamps():
    """Without an explicit DC, the framework stamps are omitted."""
    buff = _make_flesh_to_stone_petrified_buff(
        target_speed_walk=30,
        source_char_id=None,
        source_char_name="",
    )
    assert "repeated_save_ability" not in buff
    assert "repeated_save_dc" not in buff


def test_flesh_to_stone_wrapper_includes_source_bullets():
    """The wrapper appends Flesh-to-Stone-specific raw_effects."""
    buff = _make_flesh_to_stone_petrified_buff(
        target_speed_walk=30,
        source_char_id=None,
        source_char_name="",
    )
    bullets_lower = " ".join(buff["raw_effects"]).lower()
    assert "stone to flesh" in bullets_lower, buff["raw_effects"]
    assert "greater restoration" in bullets_lower, buff["raw_effects"]
    assert "3 successes" in bullets_lower or "3 con saves" in bullets_lower, (
        buff["raw_effects"]
    )


def test_flesh_to_stone_wrapper_speed_reduction_equals_base():
    buff = _make_flesh_to_stone_petrified_buff(
        target_speed_walk=40,
        source_char_id=None,
        source_char_name="",
    )
    assert buff["effects"]["speed_reduction_ft"] == 40
