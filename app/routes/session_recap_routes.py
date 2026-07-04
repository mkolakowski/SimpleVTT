"""Session recaps (v2.885.0, schema v100).

When a GM ends a session they can name it and jot GM-only notes; every
player can leave their own note for that session. Backed by two tables
keyed on ``(campaign_id, session_key)`` — see ``models.SessionRecap`` /
``SessionRecapPlayerNote`` — where ``session_key`` is the session bucket
from ``tabletop_routes._session_key_for_campaign``.

Access rules:
  - Read a recap: any campaign member. A GM sees the nickname, GM notes,
    and every player note; a player sees the nickname + only their OWN
    note (GM notes and other players' notes are never sent to them).
  - Write the recap (nickname + GM notes): GM/co-GM only.
  - Write a player note: any member, author-scoped to themselves.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..auth import require_user
from ..database import get_db
from ..models import (
    Campaign,
    SessionRecap,
    SessionRecapPlayerNote,
    User,
)
from ..realtime import hub
from .tabletop_routes import _user_can_view_campaign, _user_is_gm

router = APIRouter()

_MAX_NICKNAME = 200
_MAX_NOTES = 50_000
_MAX_SESSION_KEY = 64


def _campaign_or_403(db: Session, user: User, campaign_id: int) -> Campaign:
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")
    return campaign


def _clean_key(session_key: str) -> str:
    key = (session_key or "").strip()
    if not key or len(key) > _MAX_SESSION_KEY:
        raise HTTPException(400, "Invalid session key")
    return key


def _recap_dict(r: SessionRecap) -> dict:
    return {
        "id": r.id,
        "campaign_id": r.campaign_id,
        "session_key": r.session_key,
        "nickname": r.nickname or "",
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


@router.get("/api/campaign/{campaign_id}/session-recaps")
def list_recaps(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """All recaps for the campaign, newest first (nickname + key only —
    GM notes and player notes are fetched per-recap by the detail route)."""
    _campaign_or_403(db, user, campaign_id)
    rows = (
        db.query(SessionRecap)
        .filter(SessionRecap.campaign_id == campaign_id)
        .order_by(SessionRecap.created_at.desc())
        .all()
    )
    return {"recaps": [_recap_dict(r) for r in rows]}


@router.get("/api/campaign/{campaign_id}/session-recap/{session_key}")
def get_recap(
    campaign_id: int,
    session_key: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = _campaign_or_403(db, user, campaign_id)
    key = _clean_key(session_key)
    is_gm = _user_is_gm(user, campaign, db)
    recap = (
        db.query(SessionRecap)
        .filter(
            SessionRecap.campaign_id == campaign_id,
            SessionRecap.session_key == key,
        )
        .first()
    )
    out: dict = {
        "session_key": key,
        "exists": recap is not None,
        "nickname": (recap.nickname or "") if recap else "",
        "is_gm": is_gm,
    }
    # GM-only content: the GM notes + every player's note (with author name).
    if is_gm:
        out["gm_notes"] = (recap.gm_notes or "") if recap else ""
        notes = (
            db.query(SessionRecapPlayerNote, User.display_name)
            .join(User, User.id == SessionRecapPlayerNote.author_user_id)
            .filter(
                SessionRecapPlayerNote.campaign_id == campaign_id,
                SessionRecapPlayerNote.session_key == key,
            )
            .order_by(SessionRecapPlayerNote.updated_at.desc())
            .all()
        )
        out["player_notes"] = [
            {
                "author_user_id": n.author_user_id,
                "author_name": name or "",
                "body": n.body or "",
                "updated_at": n.updated_at.isoformat() if n.updated_at else None,
            }
            for (n, name) in notes
        ]
    # The caller's OWN note (both GM and player get this — a GM might play too).
    mine = (
        db.query(SessionRecapPlayerNote)
        .filter(
            SessionRecapPlayerNote.campaign_id == campaign_id,
            SessionRecapPlayerNote.session_key == key,
            SessionRecapPlayerNote.author_user_id == user.id,
        )
        .first()
    )
    out["my_note"] = (mine.body or "") if mine else ""
    return out


@router.put("/api/campaign/{campaign_id}/session-recap/{session_key}")
async def set_recap(
    campaign_id: int,
    session_key: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """GM/co-GM: upsert the session nickname + GM notes."""
    campaign = _campaign_or_403(db, user, campaign_id)
    if not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    key = _clean_key(session_key)
    body = await request.json()
    nickname = str(body.get("nickname", "") or "")[:_MAX_NICKNAME]
    gm_notes = str(body.get("gm_notes", "") or "")[:_MAX_NOTES]

    recap = (
        db.query(SessionRecap)
        .filter(
            SessionRecap.campaign_id == campaign_id,
            SessionRecap.session_key == key,
        )
        .first()
    )
    if recap is None:
        recap = SessionRecap(campaign_id=campaign_id, session_key=key)
        db.add(recap)
    recap.nickname = nickname
    recap.gm_notes = gm_notes
    db.commit()
    db.refresh(recap)
    # Tell members a recap exists / was renamed (nickname only — GM notes
    # never cross the wire to players).
    await hub.broadcast(
        campaign_id,
        {
            "type": "session_recap_updated",
            "data": {"session_key": key, "nickname": recap.nickname or ""},
        },
    )
    return {"ok": True, "recap": _recap_dict(recap), "gm_notes": recap.gm_notes or ""}


@router.put("/api/campaign/{campaign_id}/session-recap/{session_key}/my-note")
async def set_my_note(
    campaign_id: int,
    session_key: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Any campaign member: upsert their OWN note for the session."""
    _campaign_or_403(db, user, campaign_id)
    key = _clean_key(session_key)
    body = await request.json()
    text_body = str(body.get("body", "") or "")[:_MAX_NOTES]

    note = (
        db.query(SessionRecapPlayerNote)
        .filter(
            SessionRecapPlayerNote.campaign_id == campaign_id,
            SessionRecapPlayerNote.session_key == key,
            SessionRecapPlayerNote.author_user_id == user.id,
        )
        .first()
    )
    if note is None:
        note = SessionRecapPlayerNote(
            campaign_id=campaign_id, session_key=key, author_user_id=user.id,
        )
        db.add(note)
    note.body = text_body
    db.commit()
    db.refresh(note)
    return {
        "ok": True,
        "session_key": key,
        "body": note.body or "",
        "updated_at": note.updated_at.isoformat() if note.updated_at else None,
    }
