"""Pure, dependency-light per-(scope, id) export rate-limiter.

Generalized in v2.612.5 from ``app/user_export.py`` (the GDPR Article
15/20 cooldown) for the backup/export-import arc — the same cooldown
shape now guards the campaign / character / homebrew-item zip exports,
each with its own window. ``app/user_export.py`` is kept as a thin
back-compat shim that re-exports from here.

Kept free of FastAPI / SQLAlchemy imports so the rate-limit logic can be
unit-tested in-process without the web stack — the same pattern as
``app/audit_log.py`` and ``app/visitor_log.py`` (whose tests import the
module directly on a host that doesn't have FastAPI installed).

Best-effort: SimpleVTT runs as a single app container, so a process-local
dict suffices; it resets on restart (fail-open — the safe direction for a
data-access right, never block a legitimate request because of stale
rate-limit state). The cooldown exists to stop a hijacked session from
cheaply re-dumping a heavy archive on a loop, not to enforce a hard quota.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

# Per-(scope, id) cooldown registry — (scope, id) -> monotonic ts of the
# last export. ``scope`` is one of the keys below; ``id`` is the user id
# (for "user"/"character") or the campaign id (for "campaign"/"homebrew").
LAST_EXPORT: dict[tuple[str, int], float] = {}

# Default cooldown windows (seconds) per scope. Heavier archives get a
# longer default window. Each is overridable by env (see ``cooldown_seconds``).
_SCOPE_DEFAULTS: dict[str, int] = {
    "user": 86400,      # GDPR Article 15/20 self-serve export — 24h
    "campaign": 300,    # whole-campaign zip (media-heavy) — 5 min
    "character": 60,    # single PC sheet zip — 1 min
    "homebrew": 10,     # single homebrew record — 10 s
}

# The GDPR "user" scope keeps its original env-var name for back-compat;
# every other scope reads ``EXPORT_COOLDOWN_<SCOPE>_SECONDS``.
_SCOPE_ENV: dict[str, str] = {
    "user": "USER_DATA_EXPORT_COOLDOWN_SECONDS",
}


def cooldown_remaining(
    *, now: float, last_export_at: Optional[float], cooldown_seconds: int
) -> int:
    """Seconds remaining before the next export is allowed; 0 if allowed.

    Pure — the caller supplies the clock + last-seen timestamp so this is
    unit-testable without touching wall-time. ``cooldown_seconds <= 0``
    disables the gate entirely (returns 0).
    """
    if last_export_at is None or cooldown_seconds <= 0:
        return 0
    elapsed = now - last_export_at
    if elapsed >= cooldown_seconds:
        return 0
    return int(cooldown_seconds - elapsed)


def cooldown_seconds(scope: str) -> int:
    """Read the cooldown window for ``scope`` at call time (not cached) so
    an operator env override is honored. Unknown scopes default to 60 s."""
    env = _SCOPE_ENV.get(scope, f"EXPORT_COOLDOWN_{scope.upper()}_SECONDS")
    default = _SCOPE_DEFAULTS.get(scope, 60)
    raw = os.environ.get(env, str(default)).strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return default


def remaining_for(scope: str, id: int, *, now: float) -> int:
    """Convenience: cooldown remaining for ``(scope, id)`` using the
    process-local registry + the scope's configured window."""
    return cooldown_remaining(
        now=now,
        last_export_at=LAST_EXPORT.get((scope, id)),
        cooldown_seconds=cooldown_seconds(scope),
    )


def mark(scope: str, id: int, *, now: float) -> None:
    """Record an export at ``now`` for ``(scope, id)`` so the next request
    is gated until the window elapses."""
    LAST_EXPORT[(scope, id)] = now


def iso(dt: Optional[datetime]) -> Optional[str]:
    """ISO-8601 string for a datetime column, or None when unset."""
    return dt.isoformat() if isinstance(dt, datetime) else None
