"""Opt-in per-request visitor logging.

The P2 follow-up to the v2.424.0–v2.477.0 security/audit arc (filed
in ``TODO.md`` alongside the v2.478.0 privacy ledger). The canonical
audit log (``app/audit_log.py``) records a client IP only when a
*banning-relevant* event fires — ``auth.login_failed`` /
``api.unauthorized`` / ``api.not_found`` etc. Operators behind a
Cloudflare Tunnel who want full visitor accounting (every request,
every IP, every path, irrespective of outcome) have no built-in
surface.

This module adds an opt-in ``visitor.request`` audit event emitted
once per HTTP request by the middleware in ``app/main.py``:

    visitor.request ip=<client> ua="<agent>" method=GET path=/foo status=200 ms=12

It is **DEFAULT OFF** for two reasons — per-request logging is
high-volume (every static asset, poll, and WS upgrade) and it is
privacy-sensitive (see ``docs/wiki/privacy.md``).

Two-gate interlock — BOTH must hold for an event to fire:

  * ``VISITOR_REQUEST_LOG_ENABLED`` in {1,true,yes,on} — the explicit
    operator opt-in.
  * a **trustworthy client IP source** — ``TRUSTED_PROXY_HOPS >= 1``
    (a trusted ``X-Forwarded-For`` hop) **or** ``TRUST_CF_CONNECTING_IP``
    (Cloudflare's ``CF-Connecting-IP``, the authoritative source behind a
    pure Cloudflare Tunnel, where there are no XFF hops). Without either,
    the only IP we could record is the tunnel/proxy's own internal
    address, which is useless for visitor accounting and would mislead a
    fail2ban filter into banning the proxy itself. (v2.599.1 — the gate
    previously required a positive hop count, which wrongly closed it on
    the correct pure-CF-tunnel config ``TRUSTED_PROXY_HOPS=0`` +
    ``TRUST_CF_CONNECTING_IP=true``.)

Reusing ``audit()`` (with the same ``_extract_client_ip`` path) keeps
the recorded IP identical to what every other audit event records for
the same client, so a fail2ban filter that bans on ``visitor.request``
rate sees the same IPs as the ``auth.login_failed`` / ``api.not_found``
filters. Both gates are read at call time (never cached) so a hot env
flip is honored, mirroring the demo-magic-link / cloudflare-banning
gates.
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Optional

from .audit_log import _trust_cf_connecting_ip, _trusted_proxy_hops, audit

if TYPE_CHECKING:
    from fastapi import Request

_TRUTHY = ("1", "true", "yes", "on")


def visitor_request_log_enabled() -> bool:
    """True iff per-request visitor logging should fire.

    Read at call time (not cached) so a runtime env flip is honored.
    Requires the explicit ``VISITOR_REQUEST_LOG_ENABLED`` opt-in AND a
    trustworthy client-IP source — a trusted ``X-Forwarded-For`` hop
    (``TRUSTED_PROXY_HOPS >= 1``) OR Cloudflare's ``CF-Connecting-IP``
    (``TRUST_CF_CONNECTING_IP``). See the module docstring.
    """
    flag = os.environ.get("VISITOR_REQUEST_LOG_ENABLED", "").strip().lower() in _TRUTHY
    return flag and (_trusted_proxy_hops() >= 1 or _trust_cf_connecting_ip())


def emit_visitor_request(
    request: "Optional[Request]",
    *,
    method: str,
    path: str,
    status: int,
    ms: int,
) -> None:
    """Emit a ``visitor.request`` audit event when the two-gate
    interlock is open. No-op otherwise.

    Never raises — a logging failure must not break the response the
    middleware is about to return.
    """
    if not visitor_request_log_enabled():
        return
    try:
        audit(
            "visitor.request",
            level=logging.INFO,
            request=request,
            method=method,
            path=path,
            status=status,
            ms=ms,
        )
    except Exception:  # noqa: BLE001 — logging must never break a response
        pass
