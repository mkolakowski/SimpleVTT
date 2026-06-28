"""Admin Center — suggestion / issue-report ("Feedback") service helpers.

v2.726.0. Read + triage the ``suggestions`` table the main app fills via the
in-app "💡 Suggest" button. Pure session-taking functions (FastAPI-free) so
they're unit-testable, mirroring ``campaign_admin`` / ``user_admin``.
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..models import Suggestion

_STATUSES = ("new", "in_progress", "resolved", "wont_fix")
_KINDS = ("suggestion", "issue")


def _to_dict(s: Suggestion) -> dict:
    return {
        "id": s.id,
        "user_name": s.user_name or "—",
        "kind": s.kind or "suggestion",
        "title": s.title or "",
        "body": s.body or "",
        "page_url": s.page_url or "",
        "status": s.status or "new",
        "admin_note": s.admin_note or "",
        "created_at": s.created_at,
        "updated_at": s.updated_at,
    }


def list_suggestions(
    db: Session, status: Optional[str] = None, kind: Optional[str] = None,
) -> List[dict]:
    """All reports, newest first. Optional status / kind filters."""
    q = db.query(Suggestion)
    if status in _STATUSES:
        q = q.filter(Suggestion.status == status)
    if kind in _KINDS:
        q = q.filter(Suggestion.kind == kind)
    return [_to_dict(s) for s in q.order_by(desc(Suggestion.created_at)).all()]


def open_count(db: Session) -> int:
    """Reports still in the queue (new / in_progress)."""
    return (
        db.query(Suggestion)
        .filter(Suggestion.status.in_(("new", "in_progress")))
        .count()
    )


def update_suggestion(
    db: Session, suggestion_id: int,
    status: Optional[str] = None, admin_note: Optional[str] = None,
) -> bool:
    """Set a report's status and/or admin note. Returns False if not found
    or the status is invalid."""
    s = db.query(Suggestion).filter(Suggestion.id == suggestion_id).first()
    if not s:
        return False
    if status is not None:
        if status not in _STATUSES:
            return False
        s.status = status
    if admin_note is not None:
        s.admin_note = admin_note.strip()[:4000]
    from sqlalchemy import func
    s.updated_at = func.now()
    db.commit()
    return True


def delete_suggestion(db: Session, suggestion_id: int) -> bool:
    """Delete a report. Returns False if not found."""
    s = db.query(Suggestion).filter(Suggestion.id == suggestion_id).first()
    if not s:
        return False
    db.delete(s)
    db.commit()
    return True
