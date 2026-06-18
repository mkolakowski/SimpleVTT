"""Admin-only edge-banning endpoints + audit log — Phase 1 of
``docs/plans/cloudflare-edge-banning.md``.

Three endpoints, all under ``/admin``:

- ``POST /admin/cloudflare/ban_ip`` — call Cloudflare to add an IP
  Access Rule that blocks the IP at the edge. Writes an
  ``admin_audit_log`` row regardless of outcome (success or
  failure of the upstream API call). Requires admin auth + both
  the integration env vars AND the feature gate.

- ``POST /admin/cloudflare/unban_ip`` — remove the Cloudflare rule
  by id. Idempotent.

- ``GET /admin/cloudflare/edge_bans`` — list the audit history
  (action=``cloudflare.ban_ip``) plus the Cloudflare-side current
  rules. The audit log is the SimpleVTT-side source of truth for
  "what did this admin click"; Cloudflare is the source of truth
  for "what's banned right now at the edge."

Every call (success or failure) flows through the v2.424.0
``audit()`` helper so the fail2ban / CrowdSec consumers see
``cloudflare.ban_ok`` / ``ban_failed`` / ``unban_ok`` / ``unban_failed``
canonical lines. The lines are observational — operators may want
to scenario-tune them but the v2.424.0 fail2ban filter doesn't
include them by default.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..admin_audit import record_admin_action
from ..audit_log import audit
from ..auth import require_admin
from ..database import get_db
from ..integrations import cloudflare
from ..models import AdminAuditLog, User


router = APIRouter(prefix="/admin/cloudflare")
log = logging.getLogger(__name__)


class BanIpRequest(BaseModel):
    ip: str = Field(..., min_length=1, max_length=64)
    mode: str = Field("block", pattern="^(block|challenge|whitelist)$")
    notes: str = Field("", max_length=500)


class UnbanIpRequest(BaseModel):
    rule_id: str = Field(..., min_length=1, max_length=80)


def _gate_check() -> None:
    """Refuse with 503 (service unavailable) if the feature gate
    isn't both client-configured AND UI-enabled.

    503 instead of 404 here because the GM has admin auth (they
    proved they have a real account) — refusing with 404 would
    misleadingly imply the path doesn't exist. The UI hides the
    section when the gate is off so admins shouldn't see the
    affordance in the first place; this is defense-in-depth.
    """
    if not cloudflare.cloudflare_banning_enabled():
        raise HTTPException(
            status_code=503,
            detail="cloudflare_banning_not_configured",
        )


def _write_audit_row(
    db: Session,
    *,
    actor: User,
    action: str,
    target: str,
    cloudflare_rule_id: Optional[str] = None,
    notes: Optional[str] = None,
    scope: str = "global",
    request: Optional[Request] = None,
    audit_level: int = logging.INFO,
) -> AdminAuditLog:
    # v2.431.0: delegate to the shared helper so the canonical
    # log-line emission and the table-write happen together. The
    # existing call sites only pass success-path INFO emits; the
    # failure paths below pass WARNING explicitly.
    return record_admin_action(
        db,
        actor=actor,
        action=action,
        target=target,
        request=request,
        scope=scope,
        notes=notes,
        cloudflare_rule_id=cloudflare_rule_id,
        audit_level=audit_level,
    )


@router.post("/ban_ip")
async def ban_ip(
    payload: BanIpRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    _gate_check()
    try:
        rule_id = await cloudflare.add_ip_access_rule(
            payload.ip, mode=payload.mode, notes=payload.notes,
        )
    except cloudflare.CloudflareDisabledError:
        # Should be unreachable — _gate_check above guarantees the
        # client is configured. Belt-and-suspenders: log + 503.
        raise HTTPException(status_code=503, detail="cloudflare_disabled")
    except cloudflare.CloudflareConnectionError as e:
        _write_audit_row(
            db, actor=user, action="cloudflare.ban_failed",
            target=payload.ip, notes=f"connection: {e}",
            request=request, audit_level=logging.WARNING,
        )
        raise HTTPException(status_code=502, detail="cloudflare_unreachable")
    except cloudflare.CloudflareApiError as e:
        _write_audit_row(
            db, actor=user, action="cloudflare.ban_failed",
            target=payload.ip,
            notes=f"api: {e.status_code}: {e.body[:200]}",
            request=request, audit_level=logging.WARNING,
        )
        raise HTTPException(status_code=502, detail="cloudflare_api_error")
    row = _write_audit_row(
        db, actor=user, action="cloudflare.ban_ok",
        target=payload.ip, cloudflare_rule_id=rule_id,
        notes=payload.notes or None,
        request=request,
    )
    return {
        "ok": True,
        "rule_id": rule_id,
        "audit_id": row.id,
    }


@router.post("/unban_ip")
async def unban_ip(
    payload: UnbanIpRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    _gate_check()
    try:
        await cloudflare.remove_ip_access_rule(payload.rule_id)
    except cloudflare.CloudflareDisabledError:
        raise HTTPException(status_code=503, detail="cloudflare_disabled")
    except cloudflare.CloudflareConnectionError as e:
        _write_audit_row(
            db, actor=user, action="cloudflare.unban_failed",
            target=payload.rule_id, notes=f"connection: {e}",
            request=request, audit_level=logging.WARNING,
        )
        raise HTTPException(status_code=502, detail="cloudflare_unreachable")
    except cloudflare.CloudflareApiError as e:
        _write_audit_row(
            db, actor=user, action="cloudflare.unban_failed",
            target=payload.rule_id,
            notes=f"api: {e.status_code}: {e.body[:200]}",
            request=request, audit_level=logging.WARNING,
        )
        raise HTTPException(status_code=502, detail="cloudflare_api_error")
    row = _write_audit_row(
        db, actor=user, action="cloudflare.unban_ok",
        target=payload.rule_id,
        cloudflare_rule_id=payload.rule_id,
        request=request,
    )
    return {"ok": True, "audit_id": row.id}


@router.get("/edge_bans")
async def list_edge_bans(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    _gate_check()
    # v2.431.0: action names changed from "cloudflare.ban_ip" /
    # "cloudflare.unban_ip" to "cloudflare.ban_ok" / "cloudflare.unban_ok"
    # when the helper unification landed. Failures land at
    # "cloudflare.ban_failed" / "cloudflare.unban_failed".
    audit_rows = (
        db.query(AdminAuditLog)
        .filter(AdminAuditLog.action.in_([
            "cloudflare.ban_ok", "cloudflare.unban_ok",
            "cloudflare.ban_failed", "cloudflare.unban_failed",
        ]))
        .order_by(AdminAuditLog.created_at.desc())
        .limit(100)
        .all()
    )
    # Pull active rules from Cloudflare too. Failure here is
    # observability-only; we still return the audit history.
    upstream_rules: list[dict] = []
    upstream_error: Optional[str] = None
    try:
        upstream_rules = await cloudflare.list_ip_access_rules()
    except cloudflare.CloudflareDisabledError:
        upstream_error = "disabled"
    except cloudflare.CloudflareConnectionError:
        upstream_error = "unreachable"
    except cloudflare.CloudflareApiError as e:
        upstream_error = f"api_error_{e.status_code}"
    return {
        "ok": True,
        "audit": [
            {
                "id": r.id,
                "actor_user_id": r.actor_user_id,
                "action": r.action,
                "target": r.target,
                "cloudflare_rule_id": r.cloudflare_rule_id,
                "notes": r.notes,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in audit_rows
        ],
        "upstream": upstream_rules,
        "upstream_error": upstream_error,
    }
