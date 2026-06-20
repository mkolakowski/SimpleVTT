"""Aggregate parsed audit events into traffic statistics.

Pure + stdlib-only so it's unit-testable in-process. Takes the event
dicts produced by ``audit_parse.load_events`` and rolls them up into
the cards the dashboard renders.
"""
from __future__ import annotations

from collections import Counter
from typing import Iterable

# Event tags the dashboard surfaces as named "security signal"
# counters (the rest land in the generic by-event breakdown).
_SIGNAL_EVENTS = {
    "auth.login_failed": "Failed logins",
    "auth.login_ok": "Successful logins",
    "api.unauthorized": "401 unauthorized",
    "api.forbidden": "403 forbidden",
    "api.not_found": "404 not found",
    "visitor.request": "Visitor requests",
    "user.data_export": "Data exports",
}


def summarize(events: Iterable[dict], *, top_n_ips: int = 15, top_n_paths: int = 15) -> dict:
    """Roll a list of parsed events up into dashboard statistics.

    Returns a dict with: total event count, a by-event-tag breakdown,
    the named security-signal counters, the top source IPs, and the
    top probed paths (drawn from events that carry a ``path`` field —
    404s, 401s, visitor requests).
    """
    events = list(events)
    by_event: Counter = Counter(e.get("event", "") for e in events)
    by_ip: Counter = Counter()
    by_path: Counter = Counter()
    levels: Counter = Counter()

    for e in events:
        fields = e.get("fields") or {}
        ip = fields.get("ip")
        if ip and ip != "unknown":
            by_ip[ip] += 1
        path = fields.get("path")
        if path:
            by_path[path] += 1
        level = e.get("level")
        if level:
            levels[level] += 1

    signals = {
        label: by_event.get(tag, 0) for tag, label in _SIGNAL_EVENTS.items()
    }

    return {
        "total_events": len(events),
        "by_event": dict(by_event.most_common()),
        "by_level": dict(levels.most_common()),
        "signals": signals,
        "top_ips": by_ip.most_common(top_n_ips),
        "top_paths": by_path.most_common(top_n_paths),
        "unique_ips": len(by_ip),
    }
