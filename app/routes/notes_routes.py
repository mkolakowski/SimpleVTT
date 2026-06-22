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

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from ..auth import require_user
from ..database import get_db
from ..models import (
    Campaign,
    CampaignNote,
    Handout,
    NoteEncryptionKey,
    User,
)
from ..realtime import hub
from .tabletop_routes import _user_can_view_campaign, _user_is_gm

router = APIRouter()

# Handout image uploads (Phase 5b polish). Mirrors the portrait/token
# upload pattern: store under /static/uploads/handouts/, return the URL.
_HANDOUT_IMG_DIR = (
    Path(__file__).resolve().parent.parent / "static" / "uploads" / "handouts"
)
_HANDOUT_IMG_DIR.mkdir(parents=True, exist_ok=True)
_MAX_HANDOUT_IMG_BYTES = 8 * 1024 * 1024
_ALLOWED_HANDOUT_IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

_MAX_TITLE = 200
_MAX_BODY = 50_000
# Ciphertext envelopes ({v,iv,ct} base64) are larger than the plaintext;
# cap generously. The server treats them as opaque.
_MAX_ENC = 200_000
_MIN_KDF_ITERATIONS = 100_000
_MAX_KDF_ITERATIONS = 10_000_000


def _note_dict(n: CampaignNote) -> dict:
    """Serialize a note for the API. For a private note the plaintext
    fields are empty and the ciphertext envelopes (`enc_title` /
    `enc_body`) carry the content — only ever returned to the author
    (read path + WS are author-scoped), and useless without their key."""
    return {
        "id": n.id,
        "campaign_id": n.campaign_id,
        "author_user_id": n.author_user_id,
        "kind": n.kind,
        "visibility": n.visibility,
        "title": n.title or "",
        "body": n.body or "",
        "enc_title": n.enc_title,
        "enc_body": n.enc_body,
        "is_encrypted": bool(n.is_encrypted),
        "folder": n.folder or "",
        "pinned": bool(n.pinned),
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
        .filter(
            CampaignNote.campaign_id == campaign_id,
            # Defense in depth: a private note is loaded ONLY for its
            # author — the GM's query never even fetches another user's
            # private row (the ciphertext is unreadable anyway, but this
            # keeps it off the wire entirely). The Python _can_see_note
            # below still applies the gm_only / public rules.
            (CampaignNote.visibility != "private")
            | (CampaignNote.author_user_id == user.id),
        )
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
    - ``visibility == "private"`` → an end-to-end-encrypted player note:
      the client sends ciphertext envelopes ``enc_title`` / ``enc_body``
      (at least one), and **must not** send plaintext title/body. The
      server stores the opaque blobs (``is_encrypted=True``) and can
      never read them.
    """
    campaign = _campaign_or_403(db, user, campaign_id)
    body = await request.json()
    visibility = (body.get("visibility") or "gm_only").strip().lower()
    if visibility == "gm_only":
        if not _user_is_gm(user, campaign, db):
            raise HTTPException(403, "GM only")
        kind = "gm_note"
    elif visibility in ("public", "private"):
        kind = "player_note"  # any campaign member
    else:
        raise HTTPException(
            400, "visibility must be 'gm_only', 'public', or 'private'")

    folder = (body.get("folder") or "").strip()[:120]
    pinned = bool(body.get("pinned"))

    if visibility == "private":
        # E2E: ciphertext only — refuse to store plaintext for a private
        # note so a server-readable note can never masquerade as GM-proof.
        if (body.get("title") or "").strip() or (body.get("body") or "").strip():
            raise HTTPException(
                400, "private notes must not include plaintext title/body; "
                     "send enc_title / enc_body ciphertext")
        enc_title = body.get("enc_title") or None
        enc_body = body.get("enc_body") or None
        if not enc_title and not enc_body:
            raise HTTPException(400, "enc_title or enc_body is required")
        for blob in (enc_title, enc_body):
            if blob is not None and len(blob) > _MAX_ENC:
                raise HTTPException(400, "encrypted payload too large")
        note = CampaignNote(
            campaign_id=campaign_id, author_user_id=user.id,
            kind=kind, visibility="private",
            title=None, body=None,
            enc_title=enc_title, enc_body=enc_body, is_encrypted=True,
            folder=folder, pinned=pinned,
        )
    else:
        title = (body.get("title") or "").strip()
        note_body = (body.get("body") or "").strip()
        if not title and not note_body:
            raise HTTPException(400, "title or body is required")
        if len(title) > _MAX_TITLE:
            raise HTTPException(400, f"title exceeds {_MAX_TITLE} characters")
        if len(note_body) > _MAX_BODY:
            raise HTTPException(400, f"body exceeds {_MAX_BODY} characters")
        note = CampaignNote(
            campaign_id=campaign_id, author_user_id=user.id,
            kind=kind, visibility=visibility,
            title=title or None, body=note_body,
            folder=folder, pinned=pinned,
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
    """Edit a note (omitted fields unchanged). Write rule per
    `_can_edit_note` (gm_only → GM; public → author-or-GM; private →
    author). For a private note the client sends new `enc_title` /
    `enc_body` ciphertext and must not send plaintext title/body;
    folder/pinned are editable on any note."""
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
    if note.visibility == "private":
        # Ciphertext-only path; refuse plaintext on a private note.
        if (body.get("title") or "").strip() or (body.get("body") or "").strip():
            raise HTTPException(
                400, "private notes must not include plaintext title/body")
        if "enc_title" in body:
            note.enc_title = body.get("enc_title") or None
        if "enc_body" in body:
            note.enc_body = body.get("enc_body") or None
        for blob in (note.enc_title, note.enc_body):
            if blob is not None and len(blob) > _MAX_ENC:
                raise HTTPException(400, "encrypted payload too large")
        if not note.enc_title and not note.enc_body:
            raise HTTPException(400, "enc_title or enc_body is required")
    else:
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
        if not (note.title or "") and not (note.body or ""):
            raise HTTPException(400, "title or body is required")

    if "folder" in body:
        note.folder = (body.get("folder") or "").strip()[:120]
    if "pinned" in body:
        note.pinned = bool(body.get("pinned"))

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


@router.post("/api/campaign/{campaign_id}/handouts/upload_image")
async def upload_handout_image(
    campaign_id: int,
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Upload an image for a handout (GM/co-GM only) → returns its URL,
    which the client puts in the handout's ``image_url``. Stored under
    /static/uploads/handouts/. png/jpg/webp/gif, ≤ 8 MB."""
    campaign = _campaign_or_403(db, user, campaign_id)
    if not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    ext = Path(image.filename or "").suffix.lower() or ".png"
    if ext not in _ALLOWED_HANDOUT_IMG_EXT:
        raise HTTPException(400, "Unsupported image format (use png/jpg/webp/gif)")
    data = await image.read()
    if len(data) > _MAX_HANDOUT_IMG_BYTES:
        raise HTTPException(400, "Image exceeds 8 MB limit")
    fname = uuid.uuid4().hex + ext
    (_HANDOUT_IMG_DIR / fname).write_bytes(data)
    return {"ok": True, "image_url": "/static/uploads/handouts/" + fname}


# ───────────── Private-note encryption keys (Phase 4) ─────────────
# User-scoped (not campaign-scoped): one passphrase unlocks the user's
# private notes across all their campaigns. The server stores salt + KDF
# params + a key_check token — never the passphrase, key, or plaintext.


@router.get("/api/notes/encryption")
async def get_encryption_config(
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Return the caller's note-encryption material so the browser can
    derive the key + verify a passphrase. ``{configured: false}`` when
    the user hasn't set one up yet."""
    row = db.get(NoteEncryptionKey, user.id)
    if row is None:
        return {"configured": False, "recovery_enabled": False}
    return {
        "configured": True,
        "salt": row.salt,
        "kdf": row.kdf,
        "iterations": row.iterations,
        "key_check": row.key_check,
        "recovery_enabled": bool(row.recovery_wrapped_key),
        "recovery_wrapped_key": row.recovery_wrapped_key,
    }


@router.put("/api/notes/encryption")
async def set_encryption_config(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Set up the caller's note encryption (once). Body: ``{salt,
    iterations, key_check, kdf?}`` — all generated client-side; the
    passphrase never leaves the browser. 409 if already configured
    (changing the passphrase requires re-encrypting every note
    client-side; the only server-side path is DELETE = wipe + restart)."""
    if db.get(NoteEncryptionKey, user.id) is not None:
        raise HTTPException(409, "encryption already configured")
    body = await request.json()
    salt = (body.get("salt") or "").strip()
    key_check = (body.get("key_check") or "").strip()
    kdf = (body.get("kdf") or "PBKDF2-SHA256").strip()[:30]
    try:
        iterations = int(body.get("iterations") or 0)
    except (TypeError, ValueError):
        iterations = 0
    if not salt or len(salt) > 128:
        raise HTTPException(400, "salt is required (<=128 chars)")
    if not key_check or len(key_check) > _MAX_ENC:
        raise HTTPException(400, "key_check is required")
    if not (_MIN_KDF_ITERATIONS <= iterations <= _MAX_KDF_ITERATIONS):
        raise HTTPException(
            400, f"iterations must be between {_MIN_KDF_ITERATIONS} and "
                 f"{_MAX_KDF_ITERATIONS}")
    row = NoteEncryptionKey(
        user_id=user.id, salt=salt, kdf=kdf,
        iterations=iterations, key_check=key_check,
    )
    db.add(row)
    db.commit()
    return {"ok": True, "configured": True}


@router.put("/api/notes/encryption/recovery")
async def set_encryption_recovery(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Store (or replace) the caller's recovery wrap — the note key
    encrypted under a recovery key the user downloaded. Built client-side
    while unlocked; the server only ever sees this ciphertext envelope.
    Body: ``{recovery_wrapped_key}``. 404 if encryption isn't set up."""
    row = db.get(NoteEncryptionKey, user.id)
    if row is None:
        raise HTTPException(404, "encryption is not configured")
    body = await request.json()
    wrapped = (body.get("recovery_wrapped_key") or "").strip()
    if not wrapped or len(wrapped) > _MAX_ENC:
        raise HTTPException(400, "recovery_wrapped_key is required")
    row.recovery_wrapped_key = wrapped
    db.commit()
    return {"ok": True, "recovery_enabled": True}


@router.delete("/api/notes/encryption")
async def reset_encryption_config(
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Reset note encryption: delete the key material **and every one of
    the caller's encrypted notes** (they're unreadable without the old
    passphrase — this is the lost-passphrase recovery path, and the only
    way to change the passphrase for now). Returns the count wiped."""
    wiped = (
        db.query(CampaignNote)
        .filter(CampaignNote.author_user_id == user.id,
                CampaignNote.is_encrypted == True)  # noqa: E712
        .delete(synchronize_session=False)
    )
    row = db.get(NoteEncryptionKey, user.id)
    if row is not None:
        db.delete(row)
    db.commit()
    return {"ok": True, "notes_wiped": int(wiped)}
