"""v2.99.134 — Heroism's frightened immunity unified with the
v2.99.128 condition immunity engine.

Pre-v2.99.134 Heroism's `effects.condition_immunity_frightened:
True` marker was a per-condition boolean read only by the v2.97.43
saver-side helper `_pc_has_heroism_frightened_immunity` (to flip
the WIS save against being frightened). The v2.99.128 install-time
condition immunity gate reads a different field shape
(`effects.condition_immunity_to: [...]`), so the install path
didn't fire — Heroism'd targets could still HAVE the Frightened
buff installed if their save somehow failed despite the helper's
flip.

v2.99.134 adds `condition_immunity_to: ["frightened"]` to
Heroism's catalog entry so the install-time gate fires. The
legacy boolean stays for backward compat.

This test pins the integration at the engine level: a target with
an active Heroism buff (via `_buffs_active`) has
`_target_condition_immune(sheet, "frightened")` return True.

In-process; importing tabletop_routes pulls fastapi, so guards
the import and skips when fastapi isn't installed locally.
"""
import pytest

try:
    from app.routes.tabletop_routes import (
        _target_condition_immune,
        _SPELL_BUFF_MAP,
    )
    _IMPORT_OK = True
except ModuleNotFoundError:
    _IMPORT_OK = False


pytestmark = pytest.mark.skipif(
    not _IMPORT_OK,
    reason="fastapi not installed locally; runs in CI / docker image",
)


def test_heroism_catalog_carries_both_immunity_markers():
    """The v2.99.134 Heroism catalog entry now stamps both:
      - condition_immunity_frightened: True (v2.97.43, legacy
        per-condition boolean read by `_pc_has_heroism_frightened_
        immunity`)
      - condition_immunity_to: ["frightened"] (v2.99.134, list-
        shape canonical field read by the v2.99.128 install gate)
    """
    heroism = _SPELL_BUFF_MAP["heroism"]
    effects = heroism.get("effects") or {}
    assert effects.get("condition_immunity_frightened") is True, effects
    assert effects.get("condition_immunity_to") == ["frightened"], effects


def test_heroismed_target_blocks_frightened_install():
    """A target with an active Heroism buff (in `_buffs_active`) is
    recognized by the v2.99.128 install-time gate as immune to
    Frightened — `_target_condition_immune(sheet, "frightened")`
    returns True.
    """
    heroism_buff = _SPELL_BUFF_MAP["heroism"]
    target_sheet = {
        "_buffs_active": [heroism_buff],
    }
    assert _target_condition_immune(target_sheet, "frightened") is True


def test_heroismed_target_not_immune_to_other_conditions():
    """Heroism's immunity is specific to Frightened — other
    conditions (paralyzed, charmed, etc.) install normally.
    """
    heroism_buff = _SPELL_BUFF_MAP["heroism"]
    target_sheet = {
        "_buffs_active": [heroism_buff],
    }
    assert _target_condition_immune(target_sheet, "paralyzed") is False
    assert _target_condition_immune(target_sheet, "charmed") is False
    assert _target_condition_immune(target_sheet, "stunned") is False
