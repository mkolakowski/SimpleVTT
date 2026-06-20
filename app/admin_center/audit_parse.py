"""Parse the canonical SimpleVTT audit log into structured events.

The audit log (``/var/log/simplevtt/audit.log``) is written by
``app/audit_log.py`` through the standard-logging formatter
``%(asctime)s %(levelname)s %(name)s: %(message)s``, where the
message is a canonical line::

    <event_tag> <key>=<value> [<key>=<value> ...]

This module is pure + dependency-light (stdlib only) so the parser +
the tail helper can be unit-tested in-process without the web stack —
the same pattern as ``app/audit_log.py`` / ``app/visitor_log.py``.
"""
from __future__ import annotations

import re
import shlex
from collections import deque
from typing import Optional

# Log-line prefix: timestamp + level + logger (any logger whose name
# contains "audit", to stay robust across a logger rename) + the
# message tail. The message tail is the canonical audit line.
_PREFIX_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:,\d+)?)\s+"
    r"(?P<level>[A-Z]+)\s+"
    r"(?P<logger>[\w.]*audit[\w.]*):\s+"
    r"(?P<msg>.*)$"
)

# Canonical event line: a dotted lowercase event tag, then kv pairs.
_EVENT_RE = re.compile(
    r"^(?P<event>[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*)(?:\s+(?P<kvs>.*))?$"
)


def parse_line(line: str) -> Optional[dict]:
    """Parse one audit-log line into ``{ts, level, event, fields}``.

    Returns ``None`` for lines that aren't canonical audit events
    (app startup logs, blank lines, partial writes) so callers can
    filter them out.
    """
    m = _PREFIX_RE.match(line.rstrip("\n"))
    if not m:
        return None
    em = _EVENT_RE.match(m.group("msg").strip())
    if not em:
        return None
    fields: dict[str, str] = {}
    raw = em.group("kvs") or ""
    # shlex.split understands the double-quoted values audit() emits
    # (ua="Mozilla/5.0 (x)", path="/a b"). Fall back to a naive split
    # if a malformed line trips the tokenizer.
    try:
        tokens = shlex.split(raw)
    except ValueError:
        tokens = raw.split()
    for tok in tokens:
        if "=" in tok:
            k, v = tok.split("=", 1)
            fields[k] = v
    return {
        "ts": m.group("ts"),
        "level": m.group("level"),
        "event": em.group("event"),
        "fields": fields,
    }


def tail_lines(path: str, max_lines: int = 5000) -> list[str]:
    """Return up to the last ``max_lines`` lines of a file.

    The audit log rotates at 10 MB so a full read is bounded, but the
    deque cap keeps memory + render size predictable on a busy
    instance. Returns ``[]`` when the file is missing / unreadable
    (e.g. the volume hasn't been written yet) — the caller renders an
    empty state rather than erroring.
    """
    try:
        with open(path, "r", errors="replace") as f:
            return list(deque(f, maxlen=max_lines))
    except OSError:
        return []


def load_events(
    path: str,
    *,
    max_lines: int = 5000,
    event_prefix: Optional[str] = None,
    newest_first: bool = True,
) -> list[dict]:
    """Tail the audit log and parse it into a list of event dicts.

    ``event_prefix`` filters to events whose tag starts with the given
    string (e.g. ``"auth."`` or the exact ``"visitor.request"``).
    ``newest_first`` reverses so the most recent event is index 0,
    which is what the dashboard table wants.
    """
    events: list[dict] = []
    for line in tail_lines(path, max_lines=max_lines):
        ev = parse_line(line)
        if ev is None:
            continue
        if event_prefix and not ev["event"].startswith(event_prefix):
            continue
        events.append(ev)
    if newest_first:
        events.reverse()
    return events
