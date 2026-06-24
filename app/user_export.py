"""Back-compat shim for the GDPR Article 15/20 export cooldown helpers.

The cooldown logic was generalized into ``app/export_limit.py`` in
v2.612.5 (a per-(scope, id) limiter for the backup/export-import arc).
This module is kept so existing imports — including the host-side unit
test ``tests/harness/test_user_data_export.py`` — keep resolving.

New code should import from ``app.export_limit`` directly.
"""
from __future__ import annotations

from .export_limit import cooldown_remaining as export_cooldown_remaining  # noqa: F401
from .export_limit import iso  # noqa: F401

# Legacy per-user registry (int-keyed). The GDPR endpoint now uses the
# generalized (scope, id) registry in ``export_limit``; this name stays
# only for any out-of-tree reference.
LAST_EXPORT_MONOTONIC: dict[int, float] = {}


def export_cooldown_seconds() -> int:
    """Back-compat: the GDPR "user" scope cooldown window (seconds)."""
    from .export_limit import cooldown_seconds

    return cooldown_seconds("user")
