"""v2.159.19 — exhaustion-levels Phase 3a: speed wiring.

RAW PHB Appendix A:
  - Lv 2: speed halved
  - Lv 5: speed reduced to 0
  - cumulative — Lv 5 includes Lv 2's halving and the zero-floor on top.

These are pure-Python unit tests against the leaf helper
`app.content.effective_speed.effective_speed_walk`. The route layer
mirrors `sheet.exhaustion_level` to `combatant.exhaustion_level` in
`/set_exhaustion` and the long-rest decrement so the helper can read
the level without DB access.
"""
from app.content.effective_speed import (
    effective_speed_walk as _effective_speed_walk,
)


def test_no_exhaustion_no_penalty():
    """Lv 0 — base 30, no buffs → 30 (regression guard)."""
    assert _effective_speed_walk({"speed_walk": 30, "buffs": []}) == 30


def test_lv_1_no_penalty():
    """Lv 1 only imposes ability-check disadvantage — speed unchanged."""
    assert _effective_speed_walk({
        "speed_walk": 30, "buffs": [], "exhaustion_level": 1,
    }) == 30


def test_lv_2_halves_speed():
    """Lv 2 — speed halved (round down per integer division)."""
    assert _effective_speed_walk({
        "speed_walk": 30, "buffs": [], "exhaustion_level": 2,
    }) == 15


def test_lv_3_still_halved():
    """Lv 3 cumulatively includes Lv 2's halving — still half speed."""
    assert _effective_speed_walk({
        "speed_walk": 40, "buffs": [], "exhaustion_level": 3,
    }) == 20


def test_lv_4_still_halved():
    """Lv 4 — Lv 2's halving still in effect (HP-max halving is Lv 4,
    speed is not further halved a second time)."""
    assert _effective_speed_walk({
        "speed_walk": 30, "buffs": [], "exhaustion_level": 4,
    }) == 15


def test_lv_5_floors_to_zero():
    """Lv 5 — speed 0 regardless of bonuses or base."""
    assert _effective_speed_walk({
        "speed_walk": 30, "buffs": [], "exhaustion_level": 5,
    }) == 0


def test_lv_5_with_haste_still_zero():
    """Lv 5 is a hard floor — even with Haste's ×2 multiplier the
    result is 0 (RAW: speed reduced TO 0, not halved to 0)."""
    assert _effective_speed_walk({
        "speed_walk": 30,
        "buffs": [{"key": "haste", "effects": {"speed_multiplier": 2}}],
        "exhaustion_level": 5,
    }) == 0


def test_lv_2_composes_with_speed_reduction_buff():
    """Lv 2 halves AFTER buff reductions. Base 30 - 10 (Slow) = 20,
    then //2 = 10."""
    assert _effective_speed_walk({
        "speed_walk": 30,
        "buffs": [
            {"key": "slow", "effects": {"speed_reduction_ft": 10}},
        ],
        "exhaustion_level": 2,
    }) == 10


def test_lv_2_composes_with_speed_bonus_buff():
    """Lv 2 halves AFTER buff bonuses. Base 30 + 10 (Longstrider) = 40,
    then //2 = 20."""
    assert _effective_speed_walk({
        "speed_walk": 30,
        "buffs": [
            {"key": "longstrider",
             "effects": {"speed_bonus_ft": 10}},
        ],
        "exhaustion_level": 2,
    }) == 20


def test_lv_6_is_zero():
    """Lv 6 is also zero (death state — but the helper just returns 0
    rather than special-casing; downstream tests against the death
    state machine cover the death side)."""
    assert _effective_speed_walk({
        "speed_walk": 30, "buffs": [], "exhaustion_level": 6,
    }) == 0


def test_malformed_exhaustion_level_defaults_to_zero():
    """Defensive: a non-int exhaustion_level (string, dict, list) is
    treated as 0 — speed unchanged."""
    assert _effective_speed_walk({
        "speed_walk": 30, "buffs": [], "exhaustion_level": "two",
    }) == 30
    assert _effective_speed_walk({
        "speed_walk": 30, "buffs": [], "exhaustion_level": None,
    }) == 30
