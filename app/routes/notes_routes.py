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
from ..models import Campaign, CampaignNote, Handout, User
from ..realtime import hub
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
    """Visibility read rule: gm_only → GM/co-GM; public → any member;
    private → author only (Phase 4)."""
    if note.visibility == "gm_only":
        return _user_is_gm(user, campaign, db)
    if note.visibility == "public":
        return True  # any campaign member (membership already checked)
    if note.visibility == "private":
        return note.author_user_id == user.id
    return False


def _can_edit_note(db: Session, user: User, campaign: Campaign,
                   note: CampaignNote) -> bool:
    """Write rule: gm_only → GM/co-GM; public → author OR GM (GM may
    moderate); private → author only."""
    if note.visibility == "private":
        return note.author_user_id == user.id
    if note.visibility == "gm_only":
        return _user_is_gm(user, campaign, db)
    if note.visibility == "public":
        return note.author_user_id == user.id or _user_is_gm(user, campaign, db)
    return False


async def _broadcast_note_event(
    campaign_id: int, *, note: "CampaignNote | None" = None,
    deleted_id: "int | None" = None, visibility: str = "",
    author_user_id: "int | None" = None,
) -> None:
    """Broadcast a ``note_updated`` event scoped to who may see the note:
    public → everyone; gm_only → GMs only; private → the author only
    (via the hub's ``recipient_filter``). For a delete, pass
    ``deleted_id`` + ``visibility`` (+ ``author_user_id`` for private)
    since the row is gone. A private/gm_only note's content therefore
    never crosses the wire to a client that couldn't read it."""
    if deleted_id is not None:
        data = {"note_id": deleted_id, "deleted": True}
        vis = visibility
        author = author_user_id
    else:
        data = {"note": _note_dict(note)}
        vis = note.visibility
        author = note.author_user_id

    if vis == "public":
        rfilter = None
    elif vis == "private":
        def rfilter(ident, _a=author):  # noqa: E306
            return ident.get("user_id") == _a
    else:  # gm_only (and any unknown → GM-only, fail safe)
        def rfilter(ident):  # noqa: E306
            return bool(ident.get("is_gm"))
    await hub.broadcast(
        campaign_id, {"type": "note_updated", "data": data},
        recipient_filter=rfilter,
    )


@router.get("/api/campaign/{campaign_id}/notes")
async def list_notes(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """List the notes the caller is allowed to see: a GM/co-GM sees
    every ``gm_note`` + every ``public`` note; a player sees ``public``
    notes + their own ``private`` notes (Phase 4). Ordered pinned first,
    then most-recently-updated."""
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
    """Create a note. Body: ``{visibility?, title?, body?, folder?,
    pinned?}`` — at least one of title/body must be non-empty.

    - ``visibility`` omitted or ``"gm_only"`` → a GM prep note
      (``kind="gm_note"``); GM/co-GM only.
    - ``visibility == "public"`` → a player note visible to all campaign
      members (``kind="player_note"``); any member may create.
    - ``visibility == "private"`` → rejected for now: private notes are
      end-to-end encrypted (Phase 4) and created through the encrypted
      client, never as server-stored plaintext.
    """
    campaign = _campaign_or_403(db, user, campaign_id)
    body = await request.json()
    visibility = (body.get("visibility") or "gm_only").strip().lower()
    if visibility == "gm_only":
        if not _user_is_gm(user, campaign, db):
            raise HTTPException(403, "GM only")
        kind = "gm_note"
    elif visibility == "public":
        kind = "player_note"  # any campaign member
    elif visibility == "private":
        raise HTTPException(
            400, "private notes are end-to-end encrypted and not yet "
                 "available; create them through the encrypted client")
    else:
        raise HTTPException(400, "visibility must be 'gm_only' or 'public'")

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
        kind=kind,
        visibility=visibility,
        title=title or None,
        body=note_body,
        folder=(body.get("folder") or "").strip()[:120],
        pinned=bool(body.get("pinned")),
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    await _broadcast_note_event(campaign_id, note=note)
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
    if not _can_edit_note(db, user, campaign, note):
        raise HTTPException(403, "Not allowed to edit this note")

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
    await _broadcast_note_event(campaign_id, note=note)
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
    if not _can_edit_note(db, user, campaign, note):
        raise HTTPException(403, "Not allowed to delete this note")
    vis, author = note.visibility, note.author_user_id
    db.delete(note)
    db.commit()
    await _broadcast_note_event(
        campaign_id, deleted_id=note_id, visibility=vis, author_user_id=author)
    return {"ok": True, "deleted": note_id}


# ───────────────────────── Handouts (Phase 2) ─────────────────────────


def _handout_dict(h: Handout) -> dict:
    return {
        "id": h.id,
        "campaign_id": h.campaign_id,
        "author_user_id": h.author_user_id,
        "title": h.title,
        "body": h.body or "",
        "image_url": h.image_url,
        "folder": h.folder or "",
        "revealed": bool(h.revealed),
        "reveal_to": h.reveal_to if h.reveal_to is not None else [],
        "created_at": h.created_at.isoformat() if h.created_at else None,
        "updated_at": h.updated_at.isoformat() if h.updated_at else None,
    }


def _can_see_handout(db: Session, user: User, campaign: Campaign,
                     h: Handout) -> bool:
    """GM/co-GM always; a player only when revealed to them (all or in
    the reveal_to list)."""
    if _user_is_gm(user, campaign, db):
        return True
    if not h.revealed:
        return False
    rt = h.reveal_to
    if rt == "all":
        return True
    if isinstance(rt, list):
        return user.id in rt
    return False


@router.get("/api/campaign/{campaign_id}/handouts")
async def list_handouts(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """List handouts the caller can see — GM/co-GM see all; a player
    sees only those revealed to them."""
    campaign = _campaign_or_403(db, user, campaign_id)
    rows = (
        db.query(Handout)
        .filter(Handout.campaign_id == campaign_id)
        .order_by(Handout.updated_at.desc())
        .all()
    )
    visible = [h for h in rows if _can_see_handout(db, user, campaign, h)]
    return {"handouts": [_handout_dict(h) for h in visible]}


@router.get("/api/campaign/{campaign_id}/handouts/{handout_id}")
async def get_handout(
    campaign_id: int,
    handout_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Fetch one handout. 404 if it doesn't exist OR isn't revealed to
    the caller (never a leak that an un-revealed handout exists)."""
    campaign = _campaign_or_403(db, user, campaign_id)
    h = (
        db.query(Handout)
        .filter(Handout.id == handout_id,
                Handout.campaign_id == campaign_id)
        .first()
    )
    if not h or not _can_see_handout(db, user, campaign, h):
        raise HTTPException(404, "Handout not found")
    return {"handout": _handout_dict(h)}


@router.post("/api/campaign/{campaign_id}/handouts")
async def create_handout(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Author a handout (GM/co-GM only). Created un-revealed. Body:
    ``{title, body?, image_url?, folder?}`` — title is required."""
    campaign = _campaign_or_403(db, user, campaign_id)
    if not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")

    body = await request.json()
    title = (body.get("title") or "").strip()
    if not title:
        raise HTTPException(400, "title is required")
    if len(title) > _MAX_TITLE:
        raise HTTPException(400, f"title exceeds {_MAX_TITLE} characters")
    note_body = (body.get("body") or "").strip()
    if len(note_body) > _MAX_BODY:
        raise HTTPException(400, f"body exceeds {_MAX_BODY} characters")

    h = Handout(
        campaign_id=campaign_id,
        author_user_id=user.id,
        title=title,
        body=note_body,
        image_url=(body.get("image_url") or None),
        folder=(body.get("folder") or "").strip()[:120],
        revealed=False,
        reveal_to=[],
    )
    db.add(h)
    db.commit()
    db.refresh(h)
    return {"ok": True, "handout": _handout_dict(h)}


@router.patch("/api/campaign/{campaign_id}/handouts/{handout_id}")
async def update_handout(
    campaign_id: int,
    handout_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Edit a handout (GM/co-GM only). Updatable: title, body,
    image_url, folder. Reveal state is changed via /reveal, not here."""
    campaign = _campaign_or_403(db, user, campaign_id)
    if not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    h = (
        db.query(Handout)
        .filter(Handout.id == handout_id,
                Handout.campaign_id == campaign_id)
        .first()
    )
    if not h:
        raise HTTPException(404, "Handout not found")

    body = await request.json()
    if "title" in body:
        t = (body.get("title") or "").strip()
        if not t:
            raise HTTPException(400, "title is required")
        if len(t) > _MAX_TITLE:
            raise HTTPException(400, f"title exceeds {_MAX_TITLE} characters")
        h.title = t
    if "body" in body:
        b = (body.get("body") or "").strip()
        if len(b) > _MAX_BODY:
            raise HTTPException(400, f"body exceeds {_MAX_BODY} characters")
        h.body = b
    if "image_url" in body:
        h.image_url = body.get("image_url") or None
    if "folder" in body:
        h.folder = (body.get("folder") or "").strip()[:120]

    db.commit()
    db.refresh(h)
    return {"ok": True, "handout": _handout_dict(h)}


@router.delete("/api/campaign/{campaign_id}/handouts/{handout_id}")
async def delete_handout(
    campaign_id: int,
    handout_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Delete a handout (GM/co-GM only)."""
    campaign = _campaign_or_403(db, user, campaign_id)
    if not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    h = (
        db.query(Handout)
        .filter(Handout.id == handout_id,
                Handout.campaign_id == campaign_id)
        .first()
    )
    if not h:
        raise HTTPException(404, "Handout not found")
    db.delete(h)
    db.commit()
    return {"ok": True, "deleted": handout_id}


@router.post("/api/campaign/{campaign_id}/handouts/{handout_id}/reveal")
async def reveal_handout(
    campaign_id: int,
    handout_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Reveal (or hide) a handout (GM/co-GM only). Body:
    ``{revealed?: bool = true, to?: "all" | [user_id, …]}``.

    Broadcasts a ``handout_revealed`` WS event:
      - reveal to ``"all"`` → to every campaign client.
      - reveal to a user_id list → scoped to those users (+ GMs) via
        ``recipient_filter`` so a secret handout never toasts on a
        non-target's screen; the event carries the title + has_image.
      - hide (``revealed: false``) → a minimal ``{handout_id,
        revealed: false}`` event to everyone so any client holding it
        drops it (no title leak).
    """
    campaign = _campaign_or_403(db, user, campaign_id)
    if not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    h = (
        db.query(Handout)
        .filter(Handout.id == handout_id,
                Handout.campaign_id == campaign_id)
        .first()
    )
    if not h:
        raise HTTPException(404, "Handout not found")

    body = await request.json()
    revealed = bool(body.get("revealed", True))
    to = body.get("to", "all")
    if to == "all":
        reveal_to = "all"
    elif isinstance(to, list):
        try:
            reveal_to = [int(x) for x in to]
        except (TypeError, ValueError):
            raise HTTPException(400, "to must be 'all' or a list of user ids")
    else:
        raise HTTPException(400, "to must be 'all' or a list of user ids")

    h.revealed = revealed
    h.reveal_to = reveal_to
    db.commit()
    db.refresh(h)

    if revealed:
        data = {
            "handout_id": h.id,
            "title": h.title,
            "has_image": bool(h.image_url),
            "revealed": True,
        }
        if reveal_to == "all":
            rfilter = None
        else:
            targets = set(reveal_to)
            def rfilter(ident, _t=targets):  # noqa: E306
                return bool(ident.get("is_gm")) or ident.get("user_id") in _t
    else:
        # Hide: tell everyone holding it to drop it; no content in payload.
        data = {"handout_id": h.id, "revealed": False}
        rfilter = None

    await hub.broadcast(
        campaign_id,
        {"type": "handout_revealed", "data": data},
        recipient_filter=rfilter,
    )
    return {"ok": True, "handout": _handout_dict(h)}
