"""Reverse-DNS (PTR) lookups for IP addresses shown in the dashboard.

Reverse lookups are a network round-trip per IP, so this is **opt-in**
(the dashboard resolves only when ``?dns=1``) and results are cached
in-process for the container's lifetime. Lookups are deduped and
capped so one page render never fans out thousands of slow queries.

The resolver is injectable so the dedupe/cache/cap logic is
unit-testable without real DNS.
"""
from __future__ import annotations

import socket
from typing import Callable, Iterable, Optional

# ip -> resolved hostname (or None when there's no PTR / it failed).
_cache: dict[str, Optional[str]] = {}


def _default_resolver(ip: str, timeout: float) -> Optional[str]:
    old = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(timeout)
        host, _aliases, _addrs = socket.gethostbyaddr(ip)
        return host or None
    except (socket.herror, socket.gaierror, OSError, ValueError):
        return None
    finally:
        socket.setdefaulttimeout(old)


def reverse_lookup(
    ip: str,
    *,
    timeout: float = 1.0,
    resolver: Optional[Callable[[str, float], Optional[str]]] = None,
    cache: Optional[dict] = None,
) -> Optional[str]:
    """Resolve one IP's PTR hostname, cached. Returns None on miss."""
    cache = _cache if cache is None else cache
    if ip in cache:
        return cache[ip]
    resolver = resolver or _default_resolver
    try:
        result = resolver(ip, timeout)
    except Exception:  # noqa: BLE001 — a resolver must never break a render
        result = None
    cache[ip] = result
    return result


def resolve_many(
    ips: Iterable[str],
    *,
    limit: int = 100,
    timeout: float = 1.0,
    resolver: Optional[Callable[[str, float], Optional[str]]] = None,
    cache: Optional[dict] = None,
) -> dict[str, Optional[str]]:
    """Resolve a batch of IPs → ``{ip: hostname|None}``.

    Deduplicates (preserving first-seen order), skips empty/``unknown``
    sentinels, and caps the number of *new* (uncached) lookups at
    ``limit`` so a busy page doesn't stall on DNS. Already-cached IPs
    don't count against the cap.
    """
    cache = _cache if cache is None else cache
    out: dict[str, Optional[str]] = {}
    new_lookups = 0
    for ip in dict.fromkeys(ips):  # de-dupe, keep order
        if not ip or ip == "unknown":
            continue
        if ip in cache:
            out[ip] = cache[ip]
            continue
        if new_lookups >= limit:
            out[ip] = None  # over budget this render; left unresolved
            continue
        out[ip] = reverse_lookup(ip, timeout=timeout, resolver=resolver, cache=cache)
        new_lookups += 1
    return out
