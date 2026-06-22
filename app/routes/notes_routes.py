"""Notes & Handouts — Phase 1: GM prep notes.

See ``docs/plans/notes-and-handouts.md``. Phase 1 ships GM/co-GM prep
notes (``kind="gm_note"``, ``visibility="gm_only"``) over the
``campaign_notes`` table. Later phases extend the SAME table + the same
``/notes`` endpoints:

  - Phase 3 — player ``public`` notes (visible to all campaign members),
    delivered over WS to everyone.
  - Phase 4 — player ``private`` notes, end-to-end encrypted in the
    browser; the server stores only ``enc_title`` / ``enc_body``
    ciphertext and has no decryption path. Private-note WS events are
    scoped to the author's socket via ``hub.broadcast(...,
    recipient_filter=...)``.

The access rules below are written so those phases are additive: the
read path already filters by what the caller may see (Phase 1: a GM sees
every ``gm_note``; a non-GM sees nothing yet), and writes to a
``gm_note`` are GM-gated.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..auth import require_user
from ..database import get_db
from ..models import Campaign, CampaignNote, User
from .tabletop_routes import _user_can_view_campaign, _user_is_gm

router = APIRouter()

_MAX_TITLE = 200
_MAX_BODY = 50_000


def _note_dict(n: CampaignNote) -> dict:
    """Serialize a note for the API. Plaintext fields only — Phase 4
    will add the ciphertext envelopes for private notes."""
    return {
        "id": n.id,
        "campaign_id": n.campaign_id,
        "author_user_id": n.author_user_id,
        "kind": n.kind,
        "visibility": n.visibility,
        "title": n.title or "",
        "body": n.body or "",
        "folder": n.folder or "",
        "pinned": bool(n.pinned),
        "is_encrypted": bool(n.is_encrypted),
        "created_at": n.created_at.isoformat() if n.created_at else None,
        "updated_at": n.updated_at.isoformat() if n.updated_at else None,
    }


def _campaign_or_403(db: Session, user: User, campaign_id: int) -> Campaign:
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")
    return campaign


def _can_see_note(db: Session, user: User, campaign: Campaign,
                  note: CampaignNote) -> bool:
    """Phase 1 visibility: gm_note → GM/co-GM only. (Phase 3 adds
    public → any member; Phase 4 adds private → author only.)"""
    if note.visibility == "gm_only":
        return _user_is_gm(user, campaign, db)
    if note.visibility == "public":
        return True  # any campaign member (membership already checked)
    if note.visibility == "private":
        return note.author_user_id == user.id
    return False


@router.get("/api/campaign/{campaign_id}/notes")
async def list_notes(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """List the notes the caller is allowed to see. Phase 1: a GM/co-GM
    sees every ``gm_note`` in the campaign; a non-GM sees nothing yet
    (no public/private notes exist until Phases 3-4). Ordered pinned
    first, then most-recently-updated."""
    campaign = _campaign_or_403(db, user, campaign_id)
    rows = (
        db.query(CampaignNote)
        .filter(CampaignNote.campaign_id == campaign_id)
        .order_by(CampaignNote.pinned.desc(), CampaignNote.updated_at.desc())
        .all()
    )
    visible = [n for n in rows if _can_see_note(db, user, campaign, n)]
    return {"notes": [_note_dict(n) for n in visible]}


@router.get("/api/campaign/{campaign_id}/notes/{note_id}")
async def get_note(
    campaign_id: int,
    note_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Fetch one note by id. 404 if it doesn't exist OR the caller
    can't see it — a non-GM probing a gm_note id gets 404, never a
    leak that the note exists."""
    campaign = _campaign_or_403(db, user, campaign_id)
    note = (
        db.query(CampaignNote)
        .filter(CampaignNote.id == note_id,
                CampaignNote.campaign_id == campaign_id)
        .first()
    )
    if not note or not _can_see_note(db, user, campaign, note):
        raise HTTPException(404, "Note not found")
    return {"note": _note_dict(note)}


@router.post("/api/campaign/{campaign_id}/notes")
async def create_note(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Create a GM prep note (Phase 1: kind=gm_note, visibility=gm_only).
    GM/co-GM only. Body: ``{title?, body?, folder?, pinned?}`` — at
    least one of title/body must be non-empty."""
    campaign = _campaign_or_403(db, user, campaign_id)
    if not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")

    body = await request.json()
    title = (body.get("title") or "").strip()
    note_body = (body.get("body") or "").strip()
    if not title and not note_body:
        raise HTTPException(400, "title or body is required")
    if len(title) > _MAX_TITLE:
        raise HTTPException(400, f"title exceeds {_MAX_TITLE} characters")
    if len(note_body) > _MAX_BODY:
        raise HTTPException(400, f"body exceeds {_MAX_BODY} characters")

    note = CampaignNote(
        campaign_id=campaign_id,
        author_user_id=user.id,
        kind="gm_note",
        visibility="gm_only",
        title=title or None,
        body=note_body,
        folder=(body.get("folder") or "").strip()[:120],
        pinned=bool(body.get("pinned")),
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return {"ok": True, "note": _note_dict(note)}


@router.patch("/api/campaign/{campaign_id}/notes/{note_id}")
async def update_note(
    campaign_id: int,
    note_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Edit a note. Phase 1: gm_note → GM/co-GM only. Updatable fields:
    title, body, folder, pinned (all optional; omitted fields unchanged)."""
    campaign = _campaign_or_403(db, user, campaign_id)
    note = (
        db.query(CampaignNote)
        .filter(CampaignNote.id == note_id,
                CampaignNote.campaign_id == campaign_id)
        .first()
    )
    if not note or not _can_see_note(db, user, campaign, note):
        raise HTTPException(404, "Note not found")
    # Phase 1: only gm_notes exist, and editing one is GM-gated.
    if note.visibility == "gm_only" and not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")

    body = await request.json()
    if "title" in body:
        t = (body.get("title") or "").strip()
        if len(t) > _MAX_TITLE:
            raise HTTPException(400, f"title exceeds {_MAX_TITLE} characters")
        note.title = t or None
    if "body" in body:
        b = (body.get("body") or "").strip()
        if len(b) > _MAX_BODY:
            raise HTTPException(400, f"body exceeds {_MAX_BODY} characters")
        note.body = b
    if "folder" in body:
        note.folder = (body.get("folder") or "").strip()[:120]
    if "pinned" in body:
        note.pinned = bool(body.get("pinned"))

    if not (note.title or "") and not (note.body or ""):
        raise HTTPException(400, "title or body is required")

    db.commit()
    db.refresh(note)
    return {"ok": True, "note": _note_dict(note)}


@router.delete("/api/campaign/{campaign_id}/notes/{note_id}")
async def delete_note(
    campaign_id: int,
    note_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Delete a note. Phase 1: gm_note → GM/co-GM only."""
    campaign = _campaign_or_403(db, user, campaign_id)
    note = (
        db.query(CampaignNote)
        .filter(CampaignNote.id == note_id,
                CampaignNote.campaign_id == campaign_id)
        .first()
    )
    if not note or not _can_see_note(db, user, campaign, note):
        raise HTTPException(404, "Note not found")
    if note.visibility == "gm_only" and not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    db.delete(note)
    db.commit()
    return {"ok": True, "deleted": note_id}
