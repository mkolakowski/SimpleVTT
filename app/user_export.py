"""Pure, dependency-light helpers for the GDPR Article 15/20 user data
export endpoint (``app/routes/user_routes.py``).

Kept free of FastAPI / SQLAlchemy imports so the rate-limit logic +
serialization helpers can be unit-tested in-process without the web
stack — the same pattern as ``app/audit_log.py`` and
``app/visitor_log.py`` (whose tests import the module directly on a
host that doesn't have FastAPI installed).
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

# In-process per-user cooldown registry (user_id -> monotonic ts of the
# last export). Best-effort: SimpleVTT runs as a single app container, so
# a process-local dict suffices; it resets on restart (fail-open, the
# safe direction for a data-access right — never block a legitimate
# Article 15 request because of stale rate-limit state). The cooldown
# exists to stop a hijacked session from cheaply re-dumping the full
# record set on a loop, not to enforce a hard quota.
LAST_EXPORT_MONOTONIC: dict[int, float] = {}


def export_cooldown_remaining(
    *, now: float, last_export_at: Optional[float], cooldown_seconds: int
) -> int:
    """Seconds remaining before the user may export again; 0 if allowed.

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


def export_cooldown_seconds() -> int:
    """Read the cooldown window at call time (not cached) so an operator
    env override is honored. Default 24h per the filed TODO."""
    raw = os.environ.get("USER_DATA_EXPORT_COOLDOWN_SECONDS", "86400").strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 86400


def iso(dt: Optional[datetime]) -> Optional[str]:
    """ISO-8601 string for a datetime column, or None when unset."""
    return dt.isoformat() if isinstance(dt, datetime) else None
