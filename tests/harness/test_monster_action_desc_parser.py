"""v2.99.469 — unit tests for `_parse_monster_action_combat`.

Pure-Python test (no HTTP/WS harness). The helper derives the structured
combat fields (attack_roll / attack_bonus / damage / damage_type /
save_ability / save_dc) from an SRD-style action `desc`, so monsters
imported live from the Open5e API (whose action payloads are prose-only)
get the same usable Strike buttons as the backfilled local SRD set —
guarding against re-introducing the v2.99.465 NPC-strike bug on import.
"""
from app.content.monster_action_parse import parse_monster_action_combat as _parse


def test_parse_melee_attack_action():
    desc = ("Melee Weapon Attack: +5 to hit, reach 5 ft., one target. "
            "Hit: 6 (1d6 + 3) slashing damage.")
    out = _parse(desc)
    assert out["attack_roll"] is True
    assert out["attack_bonus"] == "+5"
    assert out["damage"] == "1d6+3"
    assert out["damage_type"] == "slashing"
    assert "save_dc" not in out


def test_parse_save_breath_weapon():
    desc = ("The dragon exhales fire in a 60-foot cone. Each creature in "
            "that area must make a DC 21 Dexterity saving throw, taking "
            "63 (18d6) fire damage on a failed save, or half as much on a "
            "successful one.")
    out = _parse(desc)
    assert out["save_dc"] == 21
    assert out["save_ability"] == "dex"
    assert out["damage"] == "18d6"
    assert out["damage_type"] == "fire"
    assert "attack_bonus" not in out


def test_parse_no_combat_fields():
    assert _parse("The creature can breathe air and water.") == {}
    assert _parse("") == {}


def test_parse_ranged_attack_negative_bonus_edge():
    # Defensive: the regex accepts a signed bonus + dice w/o a flat mod.
    desc = "Ranged Weapon Attack: +4 to hit, range 80/320 ft. Hit: 5 (2d4) piercing damage."
    out = _parse(desc)
    assert out["attack_bonus"] == "+4"
    assert out["damage"] == "2d4"
    assert out["damage_type"] == "piercing"
