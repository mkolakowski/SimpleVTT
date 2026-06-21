"""Typed audit-log emission for security-relevant events.

Per ``docs/plans/fail2ban-crowdsec-integration.md`` — a single
canonical log-line format that both fail2ban filters and CrowdSec
parsers consume natively. Every banning-relevant event flows
through ``audit()`` so the line shape stays uniform across call
sites and the X-Forwarded-For trust decision lives in one place.

Line format::

    <event_tag> <key>=<value> [<key>=<value> ...]

Where ``event_tag`` is a fixed ``subsystem.event`` string, ``ip``
and ``ua`` are required keys (extracted from ``request`` when one
is passed), and arbitrary additional key=value pairs follow.
Values with whitespace or special chars are double-quoted; bare
identifiers (ints, simple strings) pass through unquoted.

Trust model for proxy headers: nothing is trusted by default.
``TRUSTED_PROXY_HOPS=N`` opts the deploy into trusting the last N
hops of the ``X-Forwarded-For`` chain — set this only when a known
reverse proxy is in front of the app. ``TRUST_CF_CONNECTING_IP=true``
opts into trusting Cloudflare's ``CF-Connecting-IP`` header (the
reliable real-visitor source behind a Cloudflare Tunnel) — set this
only when the origin is reachable *only* via Cloudflare, or an
attacker hitting the origin directly could spoof their IP.

This module is intentionally synchronous + standard-logging-only.
No async, no third-party deps, no JSON side-channel (Phase 3 of
the plan may add one). The line goes to ``logger
"simplevtt.audit"`` which inherits the root logger's stdout
handler so docker-compose captures it.
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from fastapi import Request


_AUDIT_LOGGER = logging.getLogger("simplevtt.audit")


def _trusted_proxy_hops() -> int:
    """Read TRUSTED_PROXY_HOPS at call time so a runtime env override
    in tests doesn't get cached. The cost is negligible (single
    ``os.getenv`` + ``int``); a global ``lru_cache`` would make
    test-driven env flips invisible.
    """
    raw = os.environ.get("TRUSTED_PROXY_HOPS", "0").strip()
    try:
        n = int(raw)
    except ValueError:
        return 0
    return max(0, n)


def _trust_cf_connecting_ip() -> bool:
    """Whether to trust Cloudflare's ``CF-Connecting-IP`` header.

    Read at call time (not cached) so a runtime flip in tests/env is
    honored. Default off — trusting the header blindly would let an
    attacker who reaches the origin *directly* (bypassing Cloudflare)
    spoof their IP. Safe to enable only when the origin is reachable
    **only** through Cloudflare — e.g. a Cloudflare Tunnel (the origin
    isn't publicly exposed) or an origin firewalled to Cloudflare IPs.
    """
    return os.environ.get("TRUST_CF_CONNECTING_IP", "").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _extract_client_ip(request: "Optional[Request]") -> str:
    """Pick the source IP from a Request. Falls back to ``unknown``
    when ``request`` is None (e.g. WS handlers without the dependency
    injected, or test calls).

    Precedence:
      1. ``CF-Connecting-IP`` — when ``TRUST_CF_CONNECTING_IP`` is on.
         Cloudflare (incl. Tunnel) sets this to the real visitor IP;
         it's a single address, no chain to parse. This is the
         reliable source behind a Cloudflare Tunnel, where
         ``X-Forwarded-For`` is often absent and the immediate peer is
         a Cloudflare/cloudflared address.
      2. ``X-Forwarded-For`` — when ``TRUSTED_PROXY_HOPS`` is positive;
         takes the value at index ``-hops`` from the end so the
         closest trusted proxy in a chain is the source we read.
      3. The immediate peer (``request.client.host``).
    """
    if request is None:
        return "unknown"
    if _trust_cf_connecting_ip():
        cf = (request.headers.get("cf-connecting-ip") or "").strip()
        if cf:
            return cf
    hops = _trusted_proxy_hops()
    if hops > 0:
        xff = request.headers.get("x-forwarded-for") or ""
        if xff:
            parts = [p.strip() for p in xff.split(",") if p.strip()]
            if parts:
                # X-Forwarded-For semantics: "client, proxy1, proxy2, ..."
                # — leftmost is the original client, each later entry is a
                # proxy that appended itself. With ``hops`` trusted proxies
                # behind us, the last ``hops`` entries are proxies we
                # trust and the entry at ``parts[-(hops+1)]`` is the IP
                # the closest-trusted proxy actually saw as its client.
                # When ``hops >= len(parts)`` we've trusted past the
                # leftmost entry — clamp to index 0 and return the
                # leftmost (the original client).
                idx = max(0, len(parts) - 1 - hops)
                return parts[idx] or "unknown"
    client = request.client
    return (client.host if client else None) or "unknown"


def _extract_user_agent(request: "Optional[Request]") -> str:
    if request is None:
        return ""
    return request.headers.get("user-agent") or ""


def _format_value(v: Any) -> str:
    """Format a single value for the audit line. Bare tokens for
    ints / bools / single-word ASCII identifiers; double-quoted +
    backslash-escaped for everything else.
    """
    if v is None:
        return '""'
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    # Bare token if it's a short ASCII alphanumeric / dot / dash /
    # underscore / @ string with no whitespace — covers IPs,
    # usernames, slugs, ids. Anything else gets quoted.
    if s and all(ch.isalnum() or ch in "._-@:/+" for ch in s):
        return s
    escaped = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def audit(
    event: str,
    *,
    level: int = logging.INFO,
    request: "Optional[Request]" = None,
    **kv: Any,
) -> None:
    """Emit a canonical audit-log line.

    Args:
        event: subsystem.event tag (e.g. ``"auth.login_failed"``).
            Lowercase, dot-separated. Validated only loosely — the
            point of the typed call sites is to catch typos at
            review-time, not runtime.
        level: standard logging level. WARNING for rejection /
            failure paths, INFO for success / observational paths.
        request: FastAPI Request the event was raised against.
            When provided, ``ip`` and ``ua`` are added to the line
            automatically. Pass ``None`` for events that don't
            originate from an HTTP call (background tasks, etc.) —
            those land with ``ip=unknown ua=``.
        **kv: arbitrary additional key=value pairs. ``ip`` and
            ``ua`` overrides win over the auto-extracted versions.
    """
    pairs: list[str] = []
    auto_ip = kv.pop("ip", None) or _extract_client_ip(request)
    auto_ua = kv.pop("ua", None) if "ua" in kv else _extract_user_agent(request)
    pairs.append(f"ip={_format_value(auto_ip)}")
    pairs.append(f"ua={_format_value(auto_ua)}")
    for k, v in kv.items():
        pairs.append(f"{k}={_format_value(v)}")
    line = f"{event} " + " ".join(pairs)
    _AUDIT_LOGGER.log(level, line)
