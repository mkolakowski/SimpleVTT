"""Timezone-aware time formatting for the admin-center dashboard.

The admin center displays two kinds of times:

  * Unix-epoch values it owns (fail2ban ban timestamps) — formatted by
    ``fmt_epoch``.
  * Audit-log line timestamps written by the *app* container, which
    logs ``%(asctime)s`` in **UTC** (the app's default TZ) — converted
    by ``fmt_log_ts``.

Both are rendered in ``ADMIN_CENTER_TZ`` (default ``America/New_York``
— US Eastern, DST-aware). This is display-only: it does not change
what the app writes to the audit log, so fail2ban's time parsing is
untouched.

Pure + stdlib-only (``zoneinfo``); the tz is injectable so the
conversion is unit-testable with a fixed offset (no tzdata needed).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_DEFAULT_TZ = "America/New_York"


def display_tz_name() -> str:
    return os.environ.get("ADMIN_CENTER_TZ", _DEFAULT_TZ).strip() or _DEFAULT_TZ


def display_tz() -> tzinfo:
    """Resolve ADMIN_CENTER_TZ, falling back to UTC if the name is bad
    or the tz database is unavailable."""
    try:
        return ZoneInfo(display_tz_name())
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return timezone.utc


def fmt_epoch(t, *, tz: "tzinfo | None" = None) -> str:
    """Unix epoch → ``YYYY-MM-DD HH:MM TZ`` in the display zone."""
    if not t:
        return ""
    try:
        dt = datetime.fromtimestamp(int(t), tz=tz or display_tz())
        return dt.strftime("%Y-%m-%d %H:%M %Z")
    except (ValueError, OverflowError, OSError):
        return str(t)


def fmt_log_ts(s, *, tz: "tzinfo | None" = None) -> str:
    """Audit-log asctime (``YYYY-MM-DD HH:MM:SS,mmm``, UTC) → the
    display zone. Unparseable input is returned unchanged."""
    s = (s or "").strip()
    if not s:
        return s
    try:
        dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S,%f").replace(tzinfo=timezone.utc)
        return dt.astimezone(tz or display_tz()).strftime("%Y-%m-%d %H:%M:%S %Z")
    except ValueError:
        return s
