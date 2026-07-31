"""In-process unit tests for the main-app login brute-force throttle (v2.1039.0).

`app.login_rate_limit` is pure + stdlib-only (the caller injects the clock +
store), so these run without the container. No live integration test trips the
limit on purpose: the throttle is per-IP and the harness shares one source IP,
so locking it out would break other tests' logins.
"""
from __future__ import annotations

from app import login_rate_limit as rl

_IP = "203.0.113.7"


def test_not_locked_below_threshold():
    store: dict = {}
    for i in range(4):
        rl.record_failure(_IP, now=1000 + i, window_seconds=900, store=store)
    assert rl.lockout_remaining(_IP, now=1005, max_attempts=5, window_seconds=900, store=store) == 0


def test_locked_at_threshold():
    store: dict = {}
    for i in range(5):
        rl.record_failure(_IP, now=1000 + i, window_seconds=900, store=store)
    rem = rl.lockout_remaining(_IP, now=1005, max_attempts=5, window_seconds=900, store=store)
    assert rem > 0


def test_window_expiry_frees_ip():
    store: dict = {}
    for i in range(5):
        rl.record_failure(_IP, now=1000 + i, window_seconds=900, store=store)
    # Long past the window → old failures pruned → not locked.
    assert rl.lockout_remaining(_IP, now=1000 + 1000, max_attempts=5, window_seconds=900, store=store) == 0


def test_successful_login_reset_clears_counter():
    store: dict = {}
    for i in range(5):
        rl.record_failure(_IP, now=1000 + i, window_seconds=900, store=store)
    rl.reset(_IP, store=store)
    assert rl.lockout_remaining(_IP, now=1005, max_attempts=5, window_seconds=900, store=store) == 0


def test_per_ip_isolation():
    store: dict = {}
    for i in range(5):
        rl.record_failure("1.1.1.1", now=1000 + i, window_seconds=900, store=store)
    assert rl.lockout_remaining("2.2.2.2", now=1005, max_attempts=5, window_seconds=900, store=store) == 0
    assert rl.lockout_remaining("1.1.1.1", now=1005, max_attempts=5, window_seconds=900, store=store) > 0


def test_config_defaults_and_override(monkeypatch):
    monkeypatch.delenv("LOGIN_MAX_ATTEMPTS", raising=False)
    monkeypatch.delenv("LOGIN_WINDOW_SECONDS", raising=False)
    assert rl._cfg_max() == 10
    assert rl._cfg_window() == 900
    monkeypatch.setenv("LOGIN_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("LOGIN_WINDOW_SECONDS", "60")
    assert rl._cfg_max() == 3
    assert rl._cfg_window() == 60
