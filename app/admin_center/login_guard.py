"""Per-IP brute-force throttle for the admin-center login page.

After ``ADMIN_CENTER_LOGIN_MAX_ATTEMPTS`` failed sign-ins from one IP
within ``ADMIN_CENTER_LOGIN_WINDOW_SECONDS``, that IP is locked out for
the remainder of the window. A successful login clears its counter.

In-process + best-effort (the admin center is a single container);
resets on restart, which is the safe direction — a restart should not
keep a legitimate operator locked out. Pure + stdlib-only so the
window/threshold logic is unit-testable without the web stack; the
caller (``main.py``) supplies the client IP + clock.

Note on IP attribution behind a proxy/tunnel: the caller resolves the
client IP the same way the audit log does (honoring
``TRUSTED_PROXY_HOPS``). Without a trusted hop every request looks like
the proxy's IP, so the throttle would lock *everyone* at once — set
``TRUSTED_PROXY_HOPS`` when behind Cloudflare/nginx (see the privacy
policy + admin-center wiki).
"""
from __future__ import annotations

import os

# ip -> list of recent failure epoch timestamps.
_attempts: dict[str, list[float]] = {}


def _cfg_max() -> int:
    try:
        return max(1, int(os.environ.get("ADMIN_CENTER_LOGIN_MAX_ATTEMPTS", "5")))
    except ValueError:
        return 5


def _cfg_window() -> int:
    try:
        return max(1, int(os.environ.get("ADMIN_CENTER_LOGIN_WINDOW_SECONDS", "900")))
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
