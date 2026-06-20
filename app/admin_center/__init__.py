"""SimpleVTT Admin Center.

A small, standalone ASGI app (separate from the main app) that an
operator runs on its own port to inspect the data SimpleVTT collects:
the canonical audit log, derived traffic stats, fail2ban ban state,
and a database data-inventory summary.

It is deliberately read-only and dependency-light — it reuses the
main app's Docker image but mounts the ``audit_logs`` + ``fail2ban_data``
volumes read-only and never mutates game state. Auth is HTTP basic
(``ADMIN_CENTER_USER`` / ``ADMIN_CENTER_PASS``), independent of the
main app's session login. See ``docs/wiki/admin-center.md``.
"""
