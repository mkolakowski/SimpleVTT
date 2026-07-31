"""Per-IP brute-force throttle for the MAIN app's password login.

Mirrors ``app/admin_center/login_guard.py`` (which guards the operator app) for
the internet-facing ``POST /login``: after ``LOGIN_MAX_ATTEMPTS`` failed
sign-ins from one IP within ``LOGIN_WINDOW_SECONDS``, that IP is locked out for
the rest of the window; a successful login clears its counter.

In-process + best-effort (single container); resets on restart — the safe
direction, so a restart never keeps a legitimate user locked out. Pure +
stdlib-only so the window/threshold logic is unit-testable without the web
stack; the caller (``auth_routes.login_submit``) supplies the client IP + clock.

IP attribution behind a proxy/tunnel: the caller resolves the client IP via
``audit_log._extract_client_ip`` (honoring ``TRUSTED_PROXY_HOPS``). Without a
trusted hop every request looks like the proxy's IP, so the throttle would lock
*everyone* at once — set ``TRUSTED_PROXY_HOPS`` when behind Cloudflare/nginx.
"""
from __future__ import annotations

import os

# ip -> list of recent failure epoch timestamps.
_attempts: dict[str, list[float]] = {}


def _cfg_max() -> int:
    try:
        return max(1, int(os.environ.get("LOGIN_MAX_ATTEMPTS", "10")))
    except ValueError:
        return 10


def _cfg_window() -> int:
    try:
        return max(1, int(os.environ.get("LOGIN_WINDOW_SECONDS", "900")))
    except ValueError:
        return 900


def _prune(times: list[float], now: float, window: int) -> list[float]:
    return [t for t in times if now - t < window]


def lockout_remaining(
    ip: str,
    *,
    now: float,
    max_attempts: "int | None" = None,
    window_seconds: "int | None" = None,
    store: "dict | None" = None,
) -> int:
    """Seconds until ``ip`` may try again; 0 if not locked out."""
    max_attempts = _cfg_max() if max_attempts is None else max_attempts
    window_seconds = _cfg_window() if window_seconds is None else window_seconds
    store = _attempts if store is None else store
    times = _prune(store.get(ip, []), now, window_seconds)
    store[ip] = times
    if len(times) >= max_attempts:
        return max(1, int(window_seconds - (now - times[0])))
    return 0


def record_failure(
    ip: str,
    *,
    now: float,
    window_seconds: "int | None" = None,
    store: "dict | None" = None,
) -> None:
    """Log a failed attempt for ``ip``."""
    window_seconds = _cfg_window() if window_seconds is None else window_seconds
    store = _attempts if store is None else store
    times = _prune(store.get(ip, []), now, window_seconds)
    times.append(now)
    store[ip] = times


def reset(ip: str, *, store: "dict | None" = None) -> None:
    """Clear an IP's failure counter (call on successful login)."""
    store = _attempts if store is None else store
    store.pop(ip, None)
