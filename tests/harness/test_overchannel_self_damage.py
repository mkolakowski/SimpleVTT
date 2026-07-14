"""Unit tests for `_overchannel_self_damage_expr` — Overchannel's
escalating necrotic self-damage (Evocation Wizard Lv 14+, PHB p.117).

RAW: the first overchannel since a long rest is free; the n-th use
(n≥2) deals n d12 necrotic per spell level. So a 3rd-level spell on the
2nd use → 6d12; on the 3rd use → 9d12; a 5th-level spell on the 2nd use
→ 10d12. The end-to-end apply (HP delta) is covered by
`test_overchannel.py`; this file pins the pure dice-expression formula.

In-process tests; importing tabletop_routes pulls fastapi, so the test
guards the import with try/except + skips when fastapi isn't installed
locally. Runs in CI / docker fine.
"""
import pytest

try:
    from app.routes.tabletop_routes import _overchannel_self_damage_expr
    _IMPORT_OK = True
except ModuleNotFoundError:
    _IMPORT_OK = False


pytestmark = pytest.mark.skipif(
    not _IMPORT_OK,
    reason="fastapi not installed locally; runs in CI / docker image",
)


def test_first_use_is_free():
    assert _overchannel_self_damage_expr(1, 3) == ""


def test_second_use_level_1():
    assert _overchannel_self_damage_expr(2, 1) == "2d12"


def test_second_use_level_3_fireball():
    assert _overchannel_self_damage_expr(2, 3) == "6d12"


def test_third_use_level_3():
    assert _overchannel_self_damage_expr(3, 3) == "9d12"


def test_second_use_level_5_max():
    assert _overchannel_self_damage_expr(2, 5) == "10d12"


def test_third_use_level_5():
    assert _overchannel_self_damage_expr(3, 5) == "15d12"


def test_zero_use_number_is_free():
    assert _overchannel_self_damage_expr(0, 3) == ""


def test_zero_spell_level_is_free():
    assert _overchannel_self_damage_expr(2, 0) == ""


def test_bad_inputs_are_free():
    assert _overchannel_self_damage_expr("x", 3) == ""
    assert _overchannel_self_damage_expr(2, None) == ""
