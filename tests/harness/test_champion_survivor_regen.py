"""Unit tests for `_pc_champion_survivor_regen` — Champion Survivor (Lv 18+).

RAW (PHB p.72): a Champion Fighter Lv 18+ regains ``5 + CON mod`` HP at
the start of each of its turns if it has no more than half its HP left
(and is not at 0 HP). Champion is the SRD fighter subclass, so this is
SRD-valid.

The turn-advance hook applies the ≤-half / >0 HP gate against the live
combatant sheet; this helper only answers "does Survivor apply, and for
how much." No Lv-18 PC exists in the demo (Garrik is Lv 7), so the
regen can't ride the roster — the amount + subclass/level gate are
unit-tested directly here.

In-process tests; importing tabletop_routes pulls fastapi, so the test
guards the import with try/except + skips when fastapi isn't installed
locally. Runs in CI / docker fine.
"""
import pytest

try:
    from app.routes.tabletop_routes import _pc_champion_survivor_regen
    _IMPORT_OK = True
except ModuleNotFoundError:
    _IMPORT_OK = False


pytestmark = pytest.mark.skipif(
    not _IMPORT_OK,
    reason="fastapi not installed locally; runs in CI / docker image",
)


def _fighter(level, con=14, subclass="Champion"):
    return {
        "class": "Fighter",
        "level": level,
        "subclass": subclass,
        "abilities": {"CON": con},
    }


# ---- single-class Champion --------------------------------------------

def test_champion_below_18_no_regen():
    """Lv 17 Champion has Superior Critical but not yet Survivor."""
    assert _pc_champion_survivor_regen(_fighter(17)) is None


def test_champion_lv18_regen_5_plus_con_mod():
    """Lv 18 Champion, CON 14 (+2) → 5 + 2 = 7."""
    assert _pc_champion_survivor_regen(_fighter(18, con=14)) == 7


def test_champion_lv20_high_con():
    """Lv 20 Champion, CON 20 (+5) → 5 + 5 = 10."""
    assert _pc_champion_survivor_regen(_fighter(20, con=20)) == 10


def test_champion_default_con_is_plus_zero():
    """CON 10 (+0) → 5 + 0 = 5 (the RAW floor for average CON)."""
    assert _pc_champion_survivor_regen(_fighter(18, con=10)) == 5


def test_champion_low_con_reduces_regen():
    """CON 8 (-1) → 5 + (-1) = 4."""
    assert _pc_champion_survivor_regen(_fighter(18, con=8)) == 4


# ---- non-Champion / non-Fighter regression guards ----------------------

def test_non_champion_fighter_no_regen():
    assert _pc_champion_survivor_regen(_fighter(20, subclass="Battle Master")) is None


def test_rogue_no_regen():
    assert _pc_champion_survivor_regen(
        {"class": "Rogue", "level": 20, "abilities": {"CON": 16}}) is None


def test_none_sheet_no_regen():
    assert _pc_champion_survivor_regen(None) is None


def test_bad_level_no_regen():
    assert _pc_champion_survivor_regen(
        {"class": "Fighter", "level": "oops", "subclass": "Champion"}) is None


def test_missing_con_defaults_to_plus_zero():
    """No abilities block → CON defaults to 10 (+0) → regen 5."""
    assert _pc_champion_survivor_regen(
        {"class": "Fighter", "level": 18, "subclass": "Champion"}) == 5


# ---- multiclass path ---------------------------------------------------

def test_multiclass_champion_lv18_regen():
    sheet = {
        "class": "Wizard",
        "level": 20,
        "abilities": {"CON": 16},  # +3
        "classes": [
            {"class": "Wizard", "level": 2},
            {"class": "Fighter", "level": 18, "subclass": "Champion"},
        ],
    }
    assert _pc_champion_survivor_regen(sheet) == 8


def test_multiclass_champion_lv17_no_regen():
    sheet = {
        "class": "Wizard",
        "level": 20,
        "abilities": {"CON": 16},
        "classes": [
            {"class": "Wizard", "level": 3},
            {"class": "Fighter", "level": 17, "subclass": "Champion"},
        ],
    }
    assert _pc_champion_survivor_regen(sheet) is None
