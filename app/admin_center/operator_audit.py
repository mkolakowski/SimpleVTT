"""Append operator-attributed audit lines from the Admin Center.

The Center authenticates an **operator** (a login session string), not
an app ``User``, so it can't call ``app.admin_audit.record_admin_action``
— that writes an ``admin_audit_log`` row keyed on a ``User`` foreign key
the operator doesn't have. Instead, mutations from the Center's
write-admin surface are appended directly to the shared audit-log file —
the same stream the dashboard reads and fail2ban / CrowdSec consume —
tagged ``actor=admin-center:<operator>`` so the action is attributable.

This mirrors the marker-append pattern already used by ``/logs/clear``:
the Center process has no ``RotatingFileHandler`` attached to the
``simplevtt.audit`` logger (that's wired in ``app/main.py``, the *app*
process), so we format a canonical line by hand and append it. The
``audit_logs`` volume is mounted read-write into the Center for exactly
this (and the log-clear button).

Pure + clock-injectable so the line format is unit-testable without env
or wall-time.
"""
from __future__ import annotations

import datetime
import logging
import os
from pathlib import Path
from typing import Optional

from ..audit_log import _extract_client_ip, _extract_user_agent, _format_value

log = logging.getLogger("simplevtt.admin_center")

_LEVEL_NAMES = {
    logging.INFO: "INFO",
    logging.WARNING: "WARNING",
    logging.ERROR: "ERROR",
}


def _audit_log_path() -> str:
    """Resolve AUDIT_LOG_PATH at call time (matches app/main.py default)."""
    return os.environ.get(
        "AUDIT_LOG_PATH", "/var/log/simplevtt/audit.log"
    ).strip()


def format_line(
    event: str,
    *,
    operator: str,
    target: str,
    ip: str = "unknown",
    ua: str = "",
    notes: Optional[str] = None,
    level: int = logging.WARNING,
    now: Optional[datetime.datetime] = None,
) -> str:
    """Build one canonical audit line matching the format app/main.py's
    RotatingFileHandler writes: ``<asctime> <LEVEL> simplevtt.audit:
    <event> ip=… ua=… actor=… target=…``. UTC timestamp with a
    comma-millisecond suffix, exactly as Python's logging asctime renders
    it, so ``audit_parse.parse_line`` (and fail2ban's regex) reads it back
    intact.
    """
    now = now or datetime.datetime.utcnow()
    ts = now.strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
    level_name = _LEVEL_NAMES.get(level, "INFO")
    pairs = [
        f"ip={_format_value(ip)}",
        f"ua={_format_value(ua)}",
        f"actor={_format_value('admin-center:' + (operator or '?'))}",
        f"target={_format_value(target)}",
    ]
    if notes:
        pairs.append(f"notes={_format_value(notes)}")
    return f"{ts} {level_name} simplevtt.audit: {event} " + " ".join(pairs)


def record(
    event: str,
    *,
    operator: str,
    target: str,
    request=None,
    notes: Optional[str] = None,
    level: int = logging.WARNING,
    path: Optional[str] = None,
) -> str:
    """Append an operator audit line to the shared audit log.

    Best-effort: a write failure logs a warning but never raises — the
    mutation it records has already happened, so the audit-append must not
    turn a successful action into a 500. Returns the formatted line (also
    when no path is configured, so callers/tests can inspect it).
    """
    path = path if path is not None else _audit_log_path()
    ip = _extract_client_ip(request)
    ua = _extract_user_agent(request)
    line = format_line(
        event, operator=operator, target=target,
        ip=ip, ua=ua, notes=notes, level=level,
    )
    if not path:
        # Stdout-only deploy: still surface the event in container logs.
        log.warning("operator audit (no AUDIT_LOG_PATH): %s", line)
        return line
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception as exc:  # noqa: BLE001 — never fail the action
        log.warning("operator audit append failed (%r): %s", exc, line)
    return line
