"""v2.612.5 — generalized per-(scope, id) export rate-limiter.

Phase 1 of the backup/export-import arc (``docs/plans/backup-export-overhaul.md``).
``app/export_limit.py`` generalizes the GDPR cooldown helper into a
per-scope limiter that will guard the campaign / character / homebrew-item
zip exports in later phases. These are pure, host-side unit tests (no web
stack) — the same style as ``tests/harness/test_user_data_export.py``'s
cooldown tests, since the live 429 path is bypassed under TEST_MODE.
"""
import os

from app import export_limit
from app.export_limit import (
    cooldown_remaining,
    cooldown_seconds,
    mark,
    remaining_for,
)


# ---- pure cooldown maths (unchanged contract) -----------------------

def test_cooldown_zero_when_never_exported():
    assert cooldown_remaining(now=1000.0, last_export_at=None, cooldown_seconds=300) == 0


def test_cooldown_positive_within_window():
    assert cooldown_remaining(
        now=100_000.0, last_export_at=100_000.0 - 60, cooldown_seconds=300,
    ) == 300 - 60


def test_cooldown_zero_when_window_elapsed():
    assert cooldown_remaining(
        now=100_000.0, last_export_at=100_000.0 - 600, cooldown_seconds=300,
    ) == 0


def test_cooldown_disabled_when_window_nonpositive():
    assert cooldown_remaining(now=100.0, last_export_at=99.0, cooldown_seconds=0) == 0


# ---- per-scope window resolution ------------------------------------

def test_scope_defaults():
    # Defaults differ by scope — heavier archives get a longer window.
    assert cooldown_seconds("user") == 86400
    assert cooldown_seconds("campaign") == 300
    assert cooldown_seconds("character") == 60
    assert cooldown_seconds("homebrew") == 10
    # Unknown scope falls back to a conservative 60s.
    assert cooldown_seconds("totally-unknown") == 60


def test_scope_env_override(monkeypatch):
    # The GDPR "user" scope keeps its legacy env-var name.
    monkeypatch.setenv("USER_DATA_EXPORT_COOLDOWN_SECONDS", "111")
    assert cooldown_seconds("user") == 111
    # Other scopes read EXPORT_COOLDOWN_<SCOPE>_SECONDS.
    monkeypatch.setenv("EXPORT_COOLDOWN_CAMPAIGN_SECONDS", "42")
    assert cooldown_seconds("campaign") == 42
    # A non-integer override falls back to the scope default (not a crash).
    monkeypatch.setenv("EXPORT_COOLDOWN_CHARACTER_SECONDS", "not-a-number")
    assert cooldown_seconds("character") == 60


# ---- registry round-trip (the (scope, id) keying) -------------------

def test_registry_round_trip_is_scope_and_id_keyed(monkeypatch):
    # Isolate the process-local registry for this test.
    monkeypatch.setattr(export_limit, "LAST_EXPORT", {})
    monkeypatch.setenv("EXPORT_COOLDOWN_CAMPAIGN_SECONDS", "300")

    now = 1_000.0
    # Nothing recorded yet → allowed.
    assert remaining_for("campaign", 7, now=now) == 0

    mark("campaign", 7, now=now)
    # Immediately after → gated for the full window.
    assert remaining_for("campaign", 7, now=now) == 300
    # A different campaign id shares neither bucket → still allowed.
    assert remaining_for("campaign", 8, now=now) == 0
    # A different scope for the same id is a different bucket → allowed.
    assert remaining_for("character", 7, now=now) == 0
    # Once the window elapses → allowed again.
    assert remaining_for("campaign", 7, now=now + 300) == 0


# ---- back-compat shim still resolves --------------------------------

def test_user_export_shim_reexports():
    from app.user_export import export_cooldown_remaining, export_cooldown_seconds

    assert export_cooldown_remaining(
        now=10.0, last_export_at=None, cooldown_seconds=5,
    ) == 0
    # The shim's seconds reader maps to the "user" scope default (or env).
    assert export_cooldown_seconds() == cooldown_seconds("user")
