"""Suggestion / issue reporting — submit (any user) + triage (admin).

v2.716.0. Backs the in-app "Suggest / Report" button (tabletop Quick Links +
the global topnav). Reports are stored in the ``suggestions`` table and
triaged in the admin portal.

Endpoints:
  - ``POST /api/suggestions``            — any logged-in user files a report.
  - ``GET  /api/admin/suggestions``      — admin lists reports (JSON).
  - ``PATCH /api/admin/suggestions/{id}``— admin updates status / admin_note.
  - ``DELETE /api/admin/suggestions/{id}``— admin deletes a report.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..auth import require_admin, require_user
from ..database import get_db
from ..models import Suggestion, User

router = APIRouter()

_KINDS = ("suggestion", "issue")
_STATUSES = ("new", "in_progress", "resolved", "wont_fix")


def _suggestion_dict(s: Suggestion) -> dict:
    return {
        "id": s.id,
        "user_id": s.user_id,
        "user_name": s.user_name or "",
        "kind": s.kind or "suggestion",
        "title": s.title or "",
        "body": s.body or "",
        "page_url": s.page_url or "",
        "status": s.status or "new",
        "admin_note": s.admin_note or "",
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


@router.post("/api/suggestions")
async def create_suggestion(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """File a suggestion or issue report. Body:
    ``{kind: "suggestion"|"issue", title, body, page_url?}``. ``title`` is
    required; ``kind`` defaults to "suggestion" for unknown values."""
    body = await request.json()
    kind = str(body.get("kind") or "suggestion").strip().lower()
    if kind not in _KINDS:
        kind = "suggestion"
    title = str(body.get("title") or "").strip()[:200]
    if not title:
        raise HTTPException(400, "title is required")
    text_body = str(body.get("body") or "").strip()[:8000]
    page_url = str(body.get("page_url") or "").strip()[:500]
    s = Suggestion(
        user_id=user.id,
        user_name=getattr(user, "display_name", "") or "",
        kind=kind,
        title=title,
        body=text_body,
        page_url=page_url,
        status="new",
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return {"ok": True, "suggestion": _suggestion_dict(s)}


@router.get("/api/admin/suggestions")
def list_suggestions(
    status: str | None = None,
    kind: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Admin: list reports, newest first. Optional ``status`` / ``kind``
    query filters."""
    q = db.query(Suggestion)
    if status and status in _STATUSES:
        q = q.filter(Suggestion.status == status)
    if kind and kind in _KINDS:
        q = q.filter(Suggestion.kind == kind)
    rows = q.order_by(desc(Suggestion.created_at)).all()
    return {"ok": True, "suggestions": [_suggestion_dict(s) for s in rows]}


@router.get("/api/admin/suggestions/count")
def count_open_suggestions(
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """v2.720.0 — open-report count (status new / in_progress) for the topnav
    admin badge. Cheap COUNT query, polled by the badge JS."""
    n = (
        db.query(Suggestion)
        .filter(Suggestion.status.in_(("new", "in_progress")))
        .count()
    )
    return {"ok": True, "open": n}


@router.patch("/api/admin/suggestions/{suggestion_id}")
async def update_suggestion(
    suggestion_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Admin: update a report's ``status`` and/or ``admin_note``."""
    s = db.query(Suggestion).filter(Suggestion.id == suggestion_id).first()
    if not s:
        raise HTTPException(404, "suggestion not found")
    body = await request.json()
    if "status" in body:
        new_status = str(body.get("status") or "").strip().lower()
        if new_status not in _STATUSES:
            raise HTTPException(400, f"status must be one of {_STATUSES}")
        s.status = new_status
    if "admin_note" in body:
        s.admin_note = str(body.get("admin_note") or "").strip()[:4000]
    from sqlalchemy import func as _func
    s.updated_at = _func.now()
    db.commit()
    db.refresh(s)
    return {"ok": True, "suggestion": _suggestion_dict(s)}


@router.delete("/api/admin/suggestions/{suggestion_id}")
def delete_suggestion(
    suggestion_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Admin: delete a report."""
    s = db.query(Suggestion).filter(Suggestion.id == suggestion_id).first()
    if not s:
        raise HTTPException(404, "suggestion not found")
    db.delete(s)
    db.commit()
    return {"ok": True, "deleted": suggestion_id}
