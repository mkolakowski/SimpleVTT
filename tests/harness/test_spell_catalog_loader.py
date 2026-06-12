"""Unit tests for the spell_catalog loader + dice-expression parser.

The parser is load-bearing for the Phase 2A damage range-check
test, so it gets its own coverage. Tests run without the harness
server — pure-Python pytest cases.
"""
from __future__ import annotations

from .spell_catalog import damage_actions, dice_range, load_all_spells, save_ability_of


def test_load_all_spells_returns_non_empty():
    """The SRD spell catalog ships ~319 entries; if the loader
    returns zero, something's wrong with the path resolution or
    every file is unparseable."""
    spells = load_all_spells()
    assert len(spells) >= 200, (
        f"Catalog suspiciously small: only {len(spells)} spells loaded. "
        "Expected ~319 from app/data/local/dnd5e/spells/."
    )
    # Every entry has a slug + a name; smoke-check.
    for s in spells[:10]:
        assert s.get("slug"), s
        assert s.get("name"), s


def test_dice_range_single_die():
    assert dice_range("1d10") == (1, 10)
    assert dice_range("1d4") == (1, 4)
    assert dice_range("1d20") == (1, 20)


def test_dice_range_multi_die():
    assert dice_range("8d6") == (8, 48)
    assert dice_range("3d4") == (3, 12)
    assert dice_range("4d8") == (4, 32)


def test_dice_range_flat_bonus():
    assert dice_range("1d10+3") == (4, 13)
    assert dice_range("2d6+5") == (7, 17)
    assert dice_range("3d4+3") == (6, 15)  # Magic Missile: 3 darts × 1d4+1


def test_dice_range_negative_modifier():
    assert dice_range("1d6-1") == (0, 5)
    assert dice_range("2d8-1") == (1, 15)


def test_dice_range_mixed_dice_terms():
    # Hunter's Mark + base weapon: 1d8 weapon + 1d6 mark = (2, 14)
    assert dice_range("1d8+1d6") == (2, 14)
    # Three dice terms summed.
    assert dice_range("1d4+1d6+1d8") == (3, 18)


def test_dice_range_empty_string():
    assert dice_range("") == (0, 0)
    assert dice_range("   ") == (0, 0)


def test_dice_range_whitespace_tolerated():
    assert dice_range(" 1d10 + 3 ") == (4, 13)
    assert dice_range("8 d 6") == (8, 48)  # the parser strips spaces


def test_damage_actions_finds_damage_only():
    """A spell's actions list may include non-damage entries (utility,
    healing, save-only). damage_actions filters to entries with a
    non-empty ``damage`` field.
    """
    spell_with_damage = {
        "actions": [
            {"id": "cast", "damage": "8d6", "damage_type": "fire"},
            {"id": "ritual", "damage": "", "ritual": True},
        ]
    }
    spell_no_damage = {
        "actions": [
            {"id": "cast", "damage": "", "save_ability": "wis"},
        ]
    }
    assert len(damage_actions(spell_with_damage)) == 1
    assert damage_actions(spell_with_damage)[0]["damage_type"] == "fire"
    assert damage_actions(spell_no_damage) == []
    assert damage_actions({}) == []


def test_save_ability_of_resolution():
    """save_ability_of mirrors the endpoint: top-level first, else the
    first action that carries one; uppercased + clipped to 3 chars; ''
    when absent. The SRD stores it lowercase on actions."""
    # From an action (the SRD shape).
    assert save_ability_of({"actions": [{"id": "cast", "save_ability": "dex"}]}) == "DEX"
    # Top-level wins over an action.
    assert save_ability_of(
        {"save_ability": "con", "actions": [{"save_ability": "dex"}]}
    ) == "CON"
    # First action with a save_ability wins among several.
    assert save_ability_of(
        {"actions": [{"id": "a"}, {"save_ability": "wis"}, {"save_ability": "cha"}]}
    ) == "WIS"
    # No save anywhere → empty.
    assert save_ability_of({"actions": [{"id": "cast", "damage": "8d6"}]}) == ""
    assert save_ability_of({}) == ""
