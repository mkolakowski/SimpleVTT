"""v2.993.0 — the leveled demo PC sheets now carry the class-feature `resources`
rows the /use_* endpoints require (Rage, Second Wind, Action Surge, Indomitable,
Lay on Hands, Ki, Bardic Inspiration, Sorcery Points). Historically they shipped
the class_features text but not these counters, so those buttons 404'd.

Host-side unit test of the pure derivation helper (skips without the app deps).
"""
import pytest

pytest.importorskip("sqlalchemy")  # app.demo_campaigns imports the ORM models

from app.demo_campaigns import _class_resources  # noqa: E402


def _by_key(rows):
    return {r["key"]: r for r in rows}


def test_barbarian_rage_progression():
    assert _by_key(_class_resources("Barbarian", 5, {}))["rage"]["max"] == 3
    assert _by_key(_class_resources("Barbarian", 13, {}))["rage"]["max"] == 5
    assert _by_key(_class_resources("Barbarian", 1, {}))["rage"]["reset"] == "long"


def test_fighter_features_scale_with_level():
    r5 = _by_key(_class_resources("Fighter", 5, {}))
    assert r5["second-wind"]["max"] == 1 and r5["second-wind"]["reset"] == "short"
    assert r5["action-surge"]["max"] == 1
    assert "indomitable" not in r5           # Indomitable is level 9+
    r18 = _by_key(_class_resources("Fighter", 18, {}))
    assert r18["action-surge"]["max"] == 2   # 2 uses at 17+
    assert r18["indomitable"]["max"] == 3     # 3 uses at 17+


def test_paladin_lay_on_hands_pool():
    assert _by_key(_class_resources("Paladin", 9, {}))["lay-on-hands"]["max"] == 45
    assert _by_key(_class_resources("Paladin", 18, {}))["lay-on-hands"]["max"] == 90


def test_monk_ki_and_bard_and_sorcerer():
    assert _by_key(_class_resources("Monk", 9, {}))["ki"]["max"] == 9
    bard = _by_key(_class_resources("Bard", 9, {"CHA": 18}))["bardic-inspiration"]
    assert bard["max"] == 4 and bard["reset"] == "short"   # CHA +4, short-rest at 5+
    assert _by_key(_class_resources("Sorcerer", 18, {}))["sorcery-points"]["max"] == 18


def test_non_resource_classes_and_keys_match_endpoints():
    assert _class_resources("Wizard", 13, {}) == []
    assert _class_resources("Cleric", 8, {}) == []
    # Keys must match exactly what the /use_* endpoints look up.
    keys = set()
    for klass, lvl in [("Barbarian", 5), ("Fighter", 18), ("Paladin", 9),
                       ("Monk", 9), ("Bard", 9), ("Sorcerer", 9)]:
        keys |= {r["key"] for r in _class_resources(klass, lvl, {"CHA": 16})}
    assert keys == {"rage", "second-wind", "action-surge", "indomitable",
                    "lay-on-hands", "ki", "bardic-inspiration", "sorcery-points"}
