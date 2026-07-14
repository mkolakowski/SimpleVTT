"""Unit tests for `_attacker_crit_threshold` — Champion Fighter crit floor.

RAW: a Champion Fighter crits on a lower natural roll as it levels:
  - Improved Critical (Lv 3+) → crit on 19-20 (threshold 19).
  - Superior Critical (Lv 17+) → crit on 18-20 (threshold 18).
Champion is the SRD fighter subclass, so both thresholds are SRD-valid.

The end-to-end Improved-Critical behaviour (Garrik = Lv 7 Champion) is
covered by `test_use_attack_improved_critical.py`. Superior Critical
can't ride the demo roster (no Lv 17 PC exists), so this file unit-tests
the pure threshold helper directly across single-class + multiclass
sheets, including the Lv-17 boundary the v2.1005.x survey filed as the
last clean Phase 8 read site.

In-process tests; importing tabletop_routes pulls fastapi, so the test
guards the import with try/except + skips when fastapi isn't installed
locally. Runs in CI / docker fine.
"""
import pytest

try:
    from app.routes.tabletop_routes import _attacker_crit_threshold
    _IMPORT_OK = True
except ModuleNotFoundError:
    _IMPORT_OK = False


pytestmark = pytest.mark.skipif(
    not _IMPORT_OK,
    reason="fastapi not installed locally; runs in CI / docker image",
)


def _fighter(level, subclass="Champion"):
    return {"class": "Fighter", "level": level, "subclass": subclass}


# ---- single-class Champion --------------------------------------------

def test_champion_below_3_stays_at_20():
    assert _attacker_crit_threshold(_fighter(2)) == 20


def test_champion_lv3_improved_critical_19():
    assert _attacker_crit_threshold(_fighter(3)) == 19


def test_champion_lv16_still_improved_critical_19():
    """Just below the Superior Critical floor — must stay at 19."""
    assert _attacker_crit_threshold(_fighter(16)) == 19


def test_champion_lv17_superior_critical_18():
    """The Lv-17 boundary — Superior Critical drops the floor to 18."""
    assert _attacker_crit_threshold(_fighter(17)) == 18


def test_champion_lv20_superior_critical_18():
    assert _attacker_crit_threshold(_fighter(20)) == 18


# ---- non-Champion / non-Fighter regression guards ----------------------

def test_non_champion_fighter_stays_at_20():
    assert _attacker_crit_threshold(_fighter(17, subclass="Battle Master")) == 20


def test_rogue_stays_at_20():
    assert _attacker_crit_threshold({"class": "Rogue", "level": 17}) == 20


def test_none_sheet_defaults_to_20():
    assert _attacker_crit_threshold(None) == 20


def test_bad_level_defaults_to_20():
    assert _attacker_crit_threshold({"class": "Fighter", "level": "oops",
                                     "subclass": "Champion"}) == 20


# ---- multiclass path ---------------------------------------------------

def test_multiclass_champion_lv17_superior_critical_18():
    sheet = {
        "class": "Wizard",
        "level": 20,
        "classes": [
            {"class": "Wizard", "level": 3},
            {"class": "Fighter", "level": 17, "subclass": "Champion"},
        ],
    }
    assert _attacker_crit_threshold(sheet) == 18


def test_multiclass_champion_lv3_improved_critical_19():
    sheet = {
        "class": "Wizard",
        "level": 8,
        "classes": [
            {"class": "Wizard", "level": 5},
            {"class": "Fighter", "level": 3, "subclass": "Champion"},
        ],
    }
    assert _attacker_crit_threshold(sheet) == 19


def test_multiclass_champion_lv16_stays_19():
    sheet = {
        "class": "Wizard",
        "level": 18,
        "classes": [
            {"class": "Wizard", "level": 2},
            {"class": "Fighter", "level": 16, "subclass": "Champion"},
        ],
    }
    assert _attacker_crit_threshold(sheet) == 19
