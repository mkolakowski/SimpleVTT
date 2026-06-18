"""Shared helper for writing admin-action audit-log entries.

Wraps two concerns into one call:

1. **Persistent row** in the v2.427.0 ``admin_audit_log`` table —
   queryable history of who clicked what dangerous button.
2. **Canonical structured log line** via the v2.424.0
   ``audit_log.audit()`` helper — visible to fail2ban / CrowdSec
   consumers as ``admin.<event>`` so an operator can spot abuse
   patterns (e.g. one IP triggering many destructive actions
   rapidly = compromised admin signal).

Lives at module level (sibling of ``app/audit_log.py``) so call
sites in ``app/routes/`` import one symbol without pulling in
fastapi side-effects.

Designed to fail closed: every destructive admin path that needs
the audit log SHOULD call ``record_admin_action`` even on the
failure path so an operator can spot ``admin.<event>_failed``
patterns in the audit log too. Phase 1 wires the success-path
emissions; failed-action emissions are filed for follow-up.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from sqlalchemy.orm import Session

from .audit_log import audit
from .models import AdminAuditLog, User

if TYPE_CHECKING:
    from fastapi import Request


def record_admin_action(
    db: Session,
    *,
    actor: User,
    action: str,
    target: str,
    request: "Optional[Request]" = None,
    scope: str = "global",
    notes: Optional[str] = None,
    cloudflare_rule_id: Optional[str] = None,
    audit_level: int = logging.INFO,
) -> AdminAuditLog:
    """Record an admin-initiated action in BOTH the
    ``admin_audit_log`` table AND the canonical audit-log stream.

    Args:
        db: open session. The row is committed inline — callers
            don't need to call db.commit() afterward.
        actor: the User who triggered the action.
        action: ``subsystem.event`` slug. Convention:
            ``admin.<action>`` for destructive admin actions
            (e.g. ``admin.user_delete``, ``admin.campaign_delete``);
            ``cloudflare.<event>`` for edge-banning operations.
        target: principal subject of the action (e.g. an email,
            a campaign name, an IP, a rule id).
        request: FastAPI Request, when called from an HTTP path.
            Drives ``ip=`` + ``ua=`` extraction in the canonical
            line.
        scope: ``"global"`` (default), ``"campaign:<id>"``, or
            similar. Aids per-scope queries against the table.
        notes: free-form operator commentary stored on the row.
            Also surfaced in the canonical log line if non-empty.
        cloudflare_rule_id: for cloudflare-ban actions, the
            Cloudflare-side rule id this action emitted/removed.
        audit_level: standard ``logging`` level for the canonical
            line. Defaults to INFO; pass WARNING for failed
            actions.

    Returns the persisted ``AdminAuditLog`` row so the caller can
    surface ``audit_id`` in HTTP responses if useful.
    """
    row = AdminAuditLog(
        actor_user_id=actor.id,
        action=action,
        target=target,
        scope=scope,
        cloudflare_rule_id=cloudflare_rule_id,
        notes=notes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    audit_fields: dict = {
        "actor_id": actor.id,
        "target": target,
    }
    if scope and scope != "global":
        audit_fields["scope"] = scope
    if cloudflare_rule_id:
        audit_fields["rule_id"] = cloudflare_rule_id
    if notes:
        audit_fields["notes"] = notes
    audit(action, level=audit_level, request=request, **audit_fields)
    return row
